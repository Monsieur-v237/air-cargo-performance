# Air Cargo (Übungsfall, synthetische Daten) – Python-Analyse (läuft auf der bereinigten Excel-Datei)
import pandas as pd, numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.inspection import permutation_importance
from sklearn.metrics import roc_auc_score, confusion_matrix, precision_score, recall_score

X = "data/aircargo_bereinigt.xlsx"
df = pd.read_excel(X, sheet_name="Fact_Shipments", parse_dates=["ShipmentDate","ScheduledDeparture"])

# ---------- 1. Überblick + Fehlende Werte ----------
print(df.shape); print(df.isna().mean().sort_values(ascending=False).head(6).round(3))

# ---------- 2. Treiber: groupby statt Bauchgefühl ----------
kpi = lambda g: df.groupby(g).agg(n=("AWB_Number","size"),
        wait_median=("WaitTime_min","median"), proc_median=("ProcessingTime_min","median"),
        incident=("IncidentFlag","mean"), sla=("SLA_Met","mean")).round(3)
print(kpi("Shift")); print(kpi("AvailableResources")); print(kpi("CargoType"))

# ---------- 3. Korrelation (Pearson) + Hypothesentest ----------
num = ["NumEmployeesShift","WaitTime_min","ProcessingTime_min","Weight_kg","IncidentFlag"]
print(df[num].corr(method="spearman").round(2))        # Spearman: robust gegen Ausreißer
from scipy import stats
n_, f_ = df[df.Shift=="Nacht"].WaitTime_min.dropna(), df[df.Shift!="Nacht"].WaitTime_min.dropna()
print("Mann-Whitney Nacht vs. Rest:", stats.mannwhitneyu(n_, f_).pvalue)

# ---------- 4. Anomalien: IQR-Regel und Isolation Forest ----------
x = df.ProcessingTime_min.dropna(); q1, q3 = x.quantile([.25,.75]); hi = q3 + 1.5*(q3-q1)
df["Anomalie_IQR"] = df.ProcessingTime_min > hi
iso = IsolationForest(contamination=0.03, random_state=42)
feat = df[["ProcessingTime_min","WaitTime_min"]].dropna()
df.loc[feat.index,"Anomalie_IF"] = iso.fit_predict(feat) == -1
print("IQR-Grenze", round(hi,1), "| Ausreißer IQR:", int(df.Anomalie_IQR.sum()),
      "| davon Dangerous Goods:", int((df.Anomalie_IQR & (df.CargoType=="Dangerous Goods")).sum()))

# ---------- 5. Segmentierung (KMeans) ----------
seg = df[["Weight_kg","Volume_m3","NumPackages","ProcessingTime_min"]].dropna()
km = KMeans(4, n_init=10, random_state=42).fit(StandardScaler().fit_transform(seg))
df.loc[seg.index,"Segment"] = km.labels_
print(df.groupby("Segment")[["Weight_kg","Volume_m3","NumPackages","ProcessingTime_min"]].mean().round(1))

# ---------- 6. ML: SLA-Verletzung vorhersagen (nur Infos, die BEI ANKUNFT bekannt sind!) ----------
d = df[df.SLA_Evaluable == 1].copy()
d["Weekday"] = d.ShipmentDate.dt.dayofweek
d["Breach"] = 1 - d.SLA_Met.astype(int)
cat = ["Warehouse","Zone","Airline","CargoType","Priority","AvailableResources","Shift"]
numf = ["Weight_kg","Volume_m3","NumPackages","NumEmployeesShift","Weekday"]
# NICHT erlaubt (Leakage): ProcessingTime, ProcessingEnd, Buffer, Status, WaitTime ...
Xtr, Xte, ytr, yte = train_test_split(d[cat+numf], d.Breach, test_size=.25,
                                      random_state=42, stratify=d.Breach)
pre = ColumnTransformer([("c", OneHotEncoder(handle_unknown="ignore"), cat),
                         ("n", SimpleImputer(strategy="median"), numf)])
base = Pipeline([("p",pre),("m",LogisticRegression(max_iter=2000,class_weight="balanced"))]).fit(Xtr,ytr)
rf_model = RandomForestClassifier(300, min_samples_leaf=10, class_weight="balanced", random_state=42, n_jobs=-1)
rf   = Pipeline([("p",pre),("m",rf_model)]).fit(Xtr,ytr)
for name, m in [("LogReg",base),("RandForest",rf)]:
    p = m.predict_proba(Xte)[:,1]; pred = p > .5
    print(name, "AUC", round(roc_auc_score(yte,p),3), "Precision", round(precision_score(yte,pred),2),
          "Recall", round(recall_score(yte,pred),2), "Basisrate", round(yte.mean(),3))
pi = permutation_importance(rf, Xte, yte, scoring="roc_auc", n_repeats=15, random_state=42)
print(pd.Series(pi.importances_mean, index=Xte.columns).sort_values(ascending=False).round(4))

# ---------- 7. Was-wäre-wenn: Nachtschicht-Wartezeit auf Früh-Niveau ----------
night = (d.Shift=="Nacht")
ratio = d[d.Shift=="Früh"].WaitTime_min.median() / d[night].WaitTime_min.median()
saving = (d.WaitTime_min.fillna(0) * (1-ratio)).where(night, 0)      # gesparte Minuten (nur Nacht)
new_ok = (d.Buffer_min + saving) >= d.SLA_Threshold_min
print("SLA heute", round(d.SLA_Met.mean(),4), "-> Szenario", round(new_ok.mean(),4),
      "| vermiedene Verletzungen:", int(new_ok.sum() - d.SLA_Met.sum()))
