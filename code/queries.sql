-- ============ Q1: Gesamt-KPIs (eine Zeile) ============
SELECT COUNT(*)                                        AS shipments,
       ROUND(100.0*AVG(IsDelayed),1)                   AS delay_rate_pct,
       ROUND(100.0*AVG(IncidentFlag),1)                AS incident_rate_pct,
       ROUND(100.0*AVG(SLA_Met),1)                     AS sla_pct,          -- AVG ignoriert NULL
       ROUND(AVG(ProcessingTime_min),1)                AS avg_proc_min
FROM fact_shipments;

-- ============ Q2: KPIs je Schicht (GROUP BY + CASE) ============
SELECT Shift,
       COUNT(*)                                        AS n,
       ROUND(AVG(WaitTime_min),1)                      AS avg_wait,
       ROUND(100.0*AVG(IncidentFlag),1)                AS incident_pct,
       ROUND(100.0*AVG(SLA_Met),1)                     AS sla_pct
FROM fact_shipments
GROUP BY Shift
ORDER BY incident_pct DESC;

-- ============ Q3: MEDIAN der Wartezeit je Schicht (Fensterfunktion) ============
-- (PostgreSQL: PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY WaitTime_min))
WITH r AS (
  SELECT Shift, WaitTime_min,
         ROW_NUMBER() OVER (PARTITION BY Shift ORDER BY WaitTime_min) AS rn,
         COUNT(*)     OVER (PARTITION BY Shift)                       AS cnt
  FROM fact_shipments
  WHERE WaitTime_min IS NOT NULL
)
SELECT Shift, ROUND(AVG(WaitTime_min),1) AS median_wait
FROM r
WHERE rn IN ((cnt+1)/2, (cnt+2)/2)      -- mittleres Element bzw. die zwei mittleren
GROUP BY Shift;

-- ============ Q4: Pareto der Verzögerungsursachen (kumulativ) ============
WITH c AS (
  SELECT DelayCause, COUNT(*) AS n
  FROM fact_shipments
  WHERE IsDelayed = 1
  GROUP BY DelayCause
)
SELECT DelayCause, n,
       ROUND(100.0*n/SUM(n) OVER (),1)                               AS pct,
       ROUND(100.0*SUM(n) OVER (ORDER BY n DESC, DelayCause
                             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
             /SUM(n) OVER (),1)                                       AS cum_pct
FROM c
ORDER BY n DESC;

-- ============ Q5: Datenqualität: Duplikate und Widersprüche finden ============
-- 5a) doppelte Schlüssel (sollte nach Bereinigung 0 Zeilen liefern)
SELECT AWB_Number, COUNT(*) AS n FROM fact_shipments GROUP BY AWB_Number HAVING COUNT(*) > 1;
-- 5b) 'Abgeschlossen' ohne Endzeit (Widerspruch)
SELECT COUNT(*) AS widerspruch FROM fact_shipments WHERE Status='Abgeschlossen' AND ProcessingEnd IS NULL;
-- 5c) referentielle Integrität: Sendungen ohne Flug (LEFT JOIN ... IS NULL)
SELECT COUNT(*) AS waisen
FROM fact_shipments s LEFT JOIN dim_flights f ON f.FlightID = s.FlightID
WHERE f.FlightID IS NULL;

-- ============ Q6: SLA neu berechnen mit JOIN (Puffer vor Abflug, Schwelle je Priorität) ============
SELECT s.Priority,
       p.SLA_Puffer_min                                               AS schwelle,
       COUNT(*)                                                       AS bewertbar,
       ROUND(100.0*AVG(
         CASE WHEN (julianday(f.ScheduledDeparture)-julianday(s.ProcessingEnd))*1440 >= p.SLA_Puffer_min
              THEN 1.0 ELSE 0.0 END),1)                               AS sla_pct
FROM fact_shipments s
JOIN dim_flights    f ON f.FlightID = s.FlightID
JOIN parameter_sla  p ON p.Priority = s.Priority
WHERE s.ProcessingEnd IS NOT NULL AND s.ProcessingTime_min IS NOT NULL AND s.Status <> 'Abgebrochen'
GROUP BY s.Priority, p.SLA_Puffer_min;

-- ============ Q7: Problem-Segmente: Schicht x Ressourcen (HAVING) ============
SELECT Shift, AvailableResources,
       COUNT(*) AS n,
       ROUND(100.0*AVG(IncidentFlag),1) AS incident_pct,
       ROUND(100.0*AVG(SLA_Met),1)      AS sla_pct
FROM fact_shipments
GROUP BY Shift, AvailableResources
HAVING COUNT(*) >= 100
ORDER BY incident_pct DESC
LIMIT 5;

-- ============ Q8: Tagesvolumen + gleitender 7-Tage-Durchschnitt ============
WITH d AS (
  SELECT substr(ShipmentDate,1,10) AS tag, COUNT(*) AS n FROM fact_shipments GROUP BY 1
)
SELECT tag, n,
       ROUND(AVG(n) OVER (ORDER BY tag ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),1) AS ma7
FROM d ORDER BY tag DESC LIMIT 5;

-- ============ Q9: Schlechteste Sendung je Lager (ROW_NUMBER, Top-1 pro Gruppe) ============
SELECT Warehouse, AWB_Number, ROUND(WaitTime_min,0) AS wait_min
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY Warehouse ORDER BY WaitTime_min DESC) AS rk
      FROM fact_shipments WHERE WaitTime_min IS NOT NULL)
WHERE rk = 1;
