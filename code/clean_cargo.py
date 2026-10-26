"""Air Cargo (Übungsfall, synthetische Daten) – Datenbereinigung (Rohdaten -> sauberes Sternschema)."""
import re, numpy as np, pandas as pd
RAW = "data/aircargo_rohdaten.xlsx"
OUT = "data/aircargo_bereinigt.xlsx"
SLA_MIN = {"Critical": 120, "Express": 90, "Standard": 60}   # Puffer vor Abflug (Annahme!)
log = []   # (Schritt, Tabelle, Anzahl, Regel)

fl = pd.read_excel(RAW, sheet_name="Flights")
sh = pd.read_excel(RAW, sheet_name="Shipments")
n_fl0, n_sh0 = len(fl), len(sh)

# ---------- FLIGHTS ----------
fl["Airline"] = fl["Airline"].str.strip().str.title().replace(
    {"Cathay Pacific": "Cathay Pacific Cargo"})
log.append(("Airline-Schreibweisen vereinheitlicht", "Flights", int((x:=pd.read_excel(RAW,sheet_name="Flights")["Airline"]).isin(["Cathay Pacific","LUFTHANSA CARGO"]).sum()), "LUFTHANSA CARGO->Lufthansa Cargo; Cathay Pacific->Cathay Pacific Cargo"))
d = fl.duplicated().sum(); fl = fl.drop_duplicates("FlightID").reset_index(drop=True)
log.append(("Exakte Duplikate entfernt", "Flights", int(d), "gleiche FlightID, alle Spalten identisch"))
log.append(("ActualDeparture fehlt (bleibt leer)", "Flights", int(fl.ActualDeparture.isna().sum()), "nicht imputiert; DepartureDelay_min = leer"))
fl["DepartureDelay_min"] = (fl.ActualDeparture - fl.ScheduledDeparture).dt.total_seconds() / 60

# ---------- SHIPMENTS: Kategorien ----------
sh["Airline_ref"] = sh["Airline_ref"].str.strip().str.title().replace({"Cathay Pacific": "Cathay Pacific Cargo"})
sh = sh.rename(columns={"Airline_ref": "Airline"})
zone_raw = sh.Zone.copy()
sh["Zone"] = sh.Zone.str.upper().str.replace(r"[^A-D]", "", regex=True).str.replace("ZONE", "").str[-1]
sh["Zone"] = "Zone " + sh["Zone"]
log.append(("Zone-Varianten vereinheitlicht", "Shipments", int((zone_raw != sh.Zone).sum()), "15 Schreibweisen -> Zone A/B/C/D"))
shift_raw = sh.Shift.copy()
smap = {"FRÜH":"Früh","FRUH":"Früh","D":"Früh","DAY":"Früh","SPÄT":"Spät","SPAT":"Spät","E":"Spät","EVENING":"Spät",
        "NACHT":"Nacht","N":"Nacht","NIGHT":"Nacht"}
sh["Shift"] = sh.Shift.str.strip().str.upper().map(smap)
assert sh.Shift.notna().all()
log.append(("Shift-Varianten vereinheitlicht", "Shipments", int((shift_raw != sh.Shift).sum()), "15 Schreibweisen -> Früh/Spät/Nacht (D/Day=Früh, E/Evening=Spät, N/Night=Nacht)"))

# ---------- Zeitstempel ----------
def parse_arrival(v):
    if isinstance(v, pd.Timestamp) or hasattr(v, "year"): return pd.Timestamp(v), "ok"
    t = str(v).strip()
    for fmt in ("%d/%m/%Y %H:%M", "%Y.%m.%d-%H:%M"):
        try: return pd.Timestamp(pd.to_datetime(t, format=fmt)), "format"
        except Exception: pass
    if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", t): return pd.NaT, "nur_datum"
    return pd.NaT, "unbekannt"
res = sh.CargoArrivalTime.map(parse_arrival)
sh["CargoArrivalTime"] = pd.to_datetime([r[0] for r in res])
sh["_arr_src"] = [r[1] for r in res]
log.append(("Textformate in CargoArrivalTime geparst", "Shipments", int((sh._arr_src=="format").sum()), "dd/mm/yyyy HH:MM und yyyy.mm.dd-HH:MM -> echter Zeitstempel"))
log.append(("CargoArrivalTime nur Datum ohne Uhrzeit -> leer", "Shipments", int((sh._arr_src=="nur_datum").sum()), "Uhrzeit unbekannt, nicht geraten"))
log.append(("CargoArrivalTime 'unbekannt' -> leer", "Shipments", int((sh._arr_src=="unbekannt").sum()), "als fehlend markiert"))

# ---------- Duplikate (NACH der Normalisierung!) ----------
raw_dup = int(sh.AWB_Number.duplicated().sum())
sh["_komp"] = sh.notna().sum(axis=1) + sh.CargoArrivalTime.notna()*5
sh = sh.sort_values(["AWB_Number","_komp"], ascending=[True,False])
rej = sh[sh.AWB_Number.duplicated(keep="first")].copy()
sh = sh[~sh.AWB_Number.duplicated(keep="first")].sort_values("ShipmentDate").reset_index(drop=True)
log.append(("Duplikate (AWB_Number) entfernt", "Shipments", len(rej),
            f"{raw_dup} doppelte AWBs im Rohbestand: Kopien + Varianten nur im Format; behalten wird die vollständigste Zeile"))
rej.drop(columns=["_komp","_arr_src"]).to_excel("data/_rej.xlsx", index=False)

# ---------- Fehlende / unplausible Werte ----------
sh["Weight_Valid"] = sh.Weight_kg.between(0.5, 10000)
log.append(("Gewicht fehlt", "Shipments", int(sh.Weight_kg.isna().sum()), "bleibt leer"))
log.append(("Gewicht unplausibel (<=0 oder >10.000 kg) -> leer", "Shipments", int((sh.Weight_kg.notna() & ~sh.Weight_Valid).sum()), "Messfehler/Einheit; Originalwert verworfen"))
sh["Weight_kg"] = sh.Weight_kg.where(sh.Weight_Valid)
log.append(("Volumen fehlt", "Shipments", int(sh.Volume_m3.isna().sum()), "bleibt leer"))
log.append(("NumPackages = 0 -> leer", "Shipments", int((sh.NumPackages==0).sum()), "0 Packstücke bei existierender Sendung ist unmöglich"))
sh["NumPackages"] = sh.NumPackages.replace(0, np.nan)

# ---------- Dauern ----------
sh["WaitTime_min"] = (sh.ProcessingStart - sh.CargoArrivalTime).dt.total_seconds()/60
sh["ProcessingTime_min"] = (sh.ProcessingEnd - sh.ProcessingStart).dt.total_seconds()/60
nw = int((sh.WaitTime_min < 0).sum()); npz = int((sh.ProcessingTime_min < 0).sum())
sh["Neg_Wait"] = sh.WaitTime_min < 0; sh["Neg_Proc"] = sh.ProcessingTime_min < 0
sh.loc[sh.Neg_Wait, "WaitTime_min"] = np.nan
sh.loc[sh.Neg_Proc, "ProcessingTime_min"] = np.nan
log.append(("Negative Wartezeit -> leer", "Shipments", nw, "Ankunft nach Bearbeitungsbeginn: logisch unmöglich, Zeile bleibt erhalten"))
log.append(("Negative Bearbeitungsdauer -> leer", "Shipments", npz, "Ende vor Start: Zeile bleibt, Dauer leer"))
log.append(("ProcessingEnd fehlt (nicht imputiert)", "Shipments", int(sh.ProcessingEnd.isna().sum()),
            f"davon Status 'Abgeschlossen': {int((sh.ProcessingEnd.isna() & (sh.Status=='Abgeschlossen')).sum())} -> Widerspruch, als 'Incomplete' markiert"))
sh["DwellTime_min"] = sh.WaitTime_min + sh.ProcessingTime_min

# ---------- Flug dazu, SLA ----------
fx = fl[["FlightID","Destination","AircraftType","ScheduledDeparture","ActualDeparture","DepartureDelay_min"]]
sh = sh.merge(fx, on="FlightID", how="left", validate="m:1")
assert sh.ScheduledDeparture.notna().all()
sh["Buffer_min"] = (sh.ScheduledDeparture - sh.ProcessingEnd).dt.total_seconds()/60
sh["SLA_Threshold_min"] = sh.Priority.map(SLA_MIN)
sh["SLA_Evaluable"] = sh.ProcessingEnd.notna() & sh.ProcessingTime_min.notna() & (sh.Status != "Abgebrochen")
sh["SLA_Met"] = np.where(sh.SLA_Evaluable, (sh.Buffer_min >= sh.SLA_Threshold_min).astype(int), np.nan)
sh["IncidentFlag"] = sh.IncidentFlag.astype(int)
sh["DelayCause"] = sh.DelayCause.fillna("Keine")
sh["IsDelayed"] = (sh.Status == "Verzögert").astype(int)
sh["Incomplete_End"] = (sh.ProcessingEnd.isna() & (sh.Status == "Abgeschlossen")).astype(int)
sh["Arrival_Hour"] = sh.CargoArrivalTime.dt.hour
def flags(r):
    f=[]
    if pd.isna(r.CargoArrivalTime): f.append("Ankunft unbekannt")
    if pd.isna(r.ProcessingEnd): f.append("Ende fehlt")
    if r.Neg_Wait: f.append("Wartezeit negativ")
    if r.Neg_Proc: f.append("Dauer negativ")
    if pd.isna(r.Weight_kg): f.append("Gewicht ungültig/fehlt")
    return "; ".join(f)
sh["DQ_Flags"] = sh.apply(flags, axis=1)
sh["DQ_OK"] = (sh.DQ_Flags == "").astype(int)

cols = ["AWB_Number","FlightID","ShipmentDate","Warehouse","Zone","Airline","CargoType","Priority","Weight_kg","Volume_m3","NumPackages",
        "CargoArrivalTime","ProcessingStart","ProcessingEnd","Status","IsDelayed","IncidentFlag","DelayCause","AvailableResources","NumEmployeesShift","Shift",
        "WaitTime_min","ProcessingTime_min","DwellTime_min","ScheduledDeparture","ActualDeparture","DepartureDelay_min","Buffer_min",
        "SLA_Threshold_min","SLA_Evaluable","SLA_Met","Incomplete_End","Arrival_Hour","DQ_OK","DQ_Flags"]
fact = sh[cols]

# ---------- Dim_Date ----------
dr = pd.date_range("2026-06-30","2026-10-05")
dd = pd.DataFrame({"Date":dr}); dd["Year"]=dd.Date.dt.year; dd["Month"]=dd.Date.dt.month
dd["MonthName"]=dd.Date.dt.strftime("%Y-%m"); dd["Week"]=dd.Date.dt.isocalendar().week.astype(int)
dd["Weekday"]=dd.Date.dt.dayofweek+1
dd["WeekdayName"]=dd.Date.dt.dayofweek.map(dict(enumerate(["Mo","Di","Mi","Do","Fr","Sa","So"])))
dd["IsWeekend"]=(dd.Weekday>=6).astype(int)

par = pd.DataFrame({"Priority":list(SLA_MIN),"SLA_Puffer_min":list(SLA_MIN.values()),
    "Bemerkung":["Annahme – mit Operations Manager abstimmen"]*3})
logdf = pd.DataFrame(log, columns=["Schritt","Tabelle","Anzahl","Regel / Begründung"])
summary = pd.DataFrame([
 ("Shipments roh", n_sh0), ("Shipments sauber", len(fact)), ("Flights roh", n_fl0), ("Flights sauber", len(fl)),
 ("Zeilen mit DQ-Problem (Flag gesetzt)", int((fact.DQ_OK==0).sum())),
 ("Zeilen komplett sauber", int(fact.DQ_OK.sum())),
], columns=["Kennzahl","Wert"])
readme = pd.DataFrame({"Blatt":["Fact_Shipments","Dim_Flights","Dim_Date","Parameter_SLA","DQ_Protokoll","Entfernte_Duplikate"],
 "Inhalt":["1 Zeile pro Sendung (AWB), bereinigt, mit berechneten Spalten (Wartezeit, Bearbeitungszeit, Puffer, SLA)",
 "1 Zeile pro Flug (FlightID), Airline vereinheitlicht, Abflugverspätung",
 "Datumstabelle für Zeitintelligenz (als Date-Table markieren!)",
 "SLA-Pufferzeiten je Priorität (ANNAHME – als Power-BI-Parameter nutzen)",
 "Was wurde wie oft und warum geändert","Zeilen, die als Duplikat entfernt wurden (Nachvollziehbarkeit)"]})

rej = pd.read_excel("data/_rej.xlsx")
with pd.ExcelWriter(OUT, engine="openpyxl", datetime_format="yyyy-mm-dd hh:mm") as w:
    readme.to_excel(w,sheet_name="README",index=False)
    fact.to_excel(w,sheet_name="Fact_Shipments",index=False); fl.to_excel(w,sheet_name="Dim_Flights",index=False)
    dd.to_excel(w,sheet_name="Dim_Date",index=False); par.to_excel(w,sheet_name="Parameter_SLA",index=False)
    logdf.to_excel(w,sheet_name="DQ_Protokoll",index=False); summary.to_excel(w,sheet_name="DQ_Protokoll",index=False,startrow=len(logdf)+3)
    rej.to_excel(w,sheet_name="Entfernte_Duplikate",index=False)
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
wb = load_workbook(OUT)
for ws in wb:
    for c in ws[1]:
        c.font=Font(bold=True,color="FFFFFF"); c.fill=PatternFill("solid",fgColor="1F3A5F"); c.alignment=Alignment(vertical="center")
    ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        L=max(len(str(c.value)) if c.value is not None else 0 for c in list(col)[:200])
        ws.column_dimensions[col[0].column_letter].width=min(max(10,L+2),60)
wb["README"].column_dimensions["B"].width=110
wb["DQ_Protokoll"].column_dimensions["D"].width=100
wb["Fact_Shipments"].column_dimensions["AI"].width=45 if False else 40
wb.save(OUT)
fact.to_pickle("data/fact.pkl"); fl.to_pickle("data/flights.pkl")
print(logdf.to_string()); print(summary.to_string())
print(fact.describe().T[["count","mean","50%","min","max"]].to_string())
print(fact.SLA_Met.mean(), fact.SLA_Evaluable.sum(), fact.Shift.value_counts().to_dict(), fact.Zone.value_counts().to_dict())
