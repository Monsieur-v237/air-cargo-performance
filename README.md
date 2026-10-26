# Air-Cargo-Performance (Übungsfall)

> **Lernprojekt mit KI-generiertem Datensatz.** Kein Kunden- oder Firmenprojekt; alle Zahlen stammen aus einem mit KI erzeugten Datensatz mit absichtlich eingebauten Datenfehlern.

Übungsfall zur Prozessanalyse in einem Luftfracht-Lager: Wo geht Zeit verloren, welche Sendungen verfehlen die Pufferzeit vor dem Abflug, und woran liegt das?

Ausführliche Darstellung mit Ergebnissen: [Case Study im Portfolio](https://monsieur-v237.github.io/portfolio/air-cargo.html)

## Daten

- 2 Tabellen: `Shipments` (4.590 Zeilen roh, 4.500 nach Bereinigung) und `Flights` (356 roh, 350 nach Bereinigung), Juli bis September 2026
- Eingebaute Fehler: doppelte Sendungsnummern, gemischte Datumsformate, 15 Schreibweisen für Schicht und Zone, fehlende und unmögliche Werte
- Die Datendateien liegen nicht im Repository.

## Vorgehen

1. **Bereinigen (Power BI Desktop, Power Query):** Kategorien normalisieren, Zeitstempel parsen, *danach* Duplikate entfernen, unplausible Werte leeren statt raten, jede Änderung protokollieren
2. **KPI definieren:** SLA = Puffer zwischen Bearbeitungsende und geplantem Abflug ≥ Schwelle je Priorität; Median und P90 statt Mittelwert
3. **Ursachen analysieren:** Vergleich nach Schicht und Ressourcen, Pareto der Verzögerungsursachen, Hypothesentest, Anomalien, Vorhersagemodell, Was-wäre-wenn-Szenario

## Code

| Datei | Inhalt | Status |
|---|---|---|
| [`code/shipments.m`](code/shipments.m) | Power Query (M): Import und Bereinigung | in Power BI Desktop ausgeführt |
| [`code/clean_cargo.py`](code/clean_cargo.py) | Dieselben Bereinigungsregeln mit pandas, Datenqualitäts-Protokoll, Sternschema | ausgeführt |
| [`code/queries.sql`](code/queries.sql) | KPIs, Median per Fensterfunktion, kumulatives Pareto, Anti-Join, Top-1 je Gruppe | in SQLite ausgeführt |
| [`code/solution.py`](code/solution.py) | Mann-Whitney-Test, IQR und Isolation Forest, KMeans, Logistische Regression und Random Forest, Permutation Importance, Szenario | ausgeführt |
| [`code/incidents.ts`](code/incidents.ts) | Erkennung kritischer Sendungen und Teams-Nachricht (strikt typisiert) | kompiliert (`tsc --strict`) |
| [`code/measures.dax`](code/measures.dax) | DAX-Measures (SLA, Median, P90, Pareto, Datenqualität) | Entwurf, Logik gegen pandas geprüft |

Python-Pakete: `pandas`, `numpy`, `scipy`, `scikit-learn`, `openpyxl`. Die Pfade im Code erwarten die Daten unter `data/`.

## Ergebnisse (auf dem KI-generierten Datensatz)

- **Nachtschicht als Engpass:** Median-Wartezeit 46,8 min (Früh 28,1, Spät 25,7), Incident-Rate 12,3 % statt 6,5–6,9 %, SLA-Quote 86,2 % statt 90,8–91,4 %.
- **Datenqualität:** 90 doppelte Sendungsnummern, davon 25 erst nach Normalisierung erkennbar; 175 Sendungen mit Status „Abgeschlossen“ ohne Endzeit.
- **Keine dominante Ursache:** Die drei häufigsten Verzögerungsursachen erklären zusammen nur 45,5 % der Verzögerungen. Das Vorhersagemodell erreicht nur eine AUC von etwa 0,62–0,64.

## Grenzen

- KI-generierter Datensatz: Die Ergebnisse sagen nichts über einen echten Betrieb aus.
- Die SLA-Schwellen (Critical 120, Express 90, Standard 60 Minuten) sind Annahmen.
- Korrelation ist keine Kausalität: Der Effekt der Nachtschicht wäre in der Praxis mit Vorher/Nachher und Vergleichsgruppe zu prüfen.
- Das Dashboard existiert nur als PowerPoint-Mockup, nicht als Power-BI-Bericht.
