// ===== Query "Flights" =====
let
    Source   = Excel.Workbook(File.Contents("C:\Daten\aircargo_rohdaten.xlsx"), null, true),
    Sheet    = Source{[Item = "Flights", Kind = "Sheet"]}[Data],
    Promoted = Table.PromoteHeaders(Sheet, [PromoteAllScalars = true]),
    Typed    = Table.TransformColumnTypes(Promoted, {
                  {"ScheduledDeparture", type datetime}, {"ActualDeparture", type datetime},
                  {"FlightID", type text}, {"Airline", type text}}),
    Airline  = Table.TransformColumns(Typed, {{"Airline",
                  each let t = Text.Proper(Text.Trim(_)) in
                       if t = "Cathay Pacific" then "Cathay Pacific Cargo" else t, type text}}),
    Distinct = Table.Distinct(Airline, {"FlightID"}),
    Delay    = Table.AddColumn(Distinct, "DepartureDelay_min",
                  each if [ActualDeparture] = null then null
                       else Duration.TotalMinutes([ActualDeparture] - [ScheduledDeparture]), type number)
in
    Delay

// ===== Query "Shipments" =====
let
    Source   = Excel.Workbook(File.Contents("C:\Daten\aircargo_rohdaten.xlsx"), null, true),
    Sheet    = Source{[Item = "Shipments", Kind = "Sheet"]}[Data],
    Promoted = Table.PromoteHeaders(Sheet, [PromoteAllScalars = true]),

    // 1) Kategorien normalisieren (VOR dem Duplikat-Entfernen!)
    ZoneFix  = Table.TransformColumns(Promoted, {{"Zone",
                  each "Zone " & Text.End(Text.Select(Text.Upper(_), {"A".."Z"}), 1), type text}}),
    ShiftFix = Table.TransformColumns(ZoneFix, {{"Shift", each
                  let u = Text.Upper(Text.Trim(_)) in
                      if List.Contains({"FRÜH", "FRUH", "D", "DAY"}, u)       then "Früh"
                      else if List.Contains({"SPÄT", "SPAT", "E", "EVENING"}, u) then "Spät"
                      else if List.Contains({"NACHT", "N", "NIGHT"}, u)       then "Nacht"
                      else null, type text}}),
    AirFix   = Table.TransformColumns(ShiftFix, {{"Airline_ref",
                  each let t = Text.Proper(Text.Trim(_)) in
                       if t = "Cathay Pacific" then "Cathay Pacific Cargo" else t, type text}}),

    // 2) Gemischte Datumsformate: echte Datumswerte behalten, Texte mit try/otherwise parsen
    ParseDT  = (v as any) as nullable datetime =>
                  if v is null then null
                  else if v is datetime then v
                  else let t = Text.Trim(Text.From(v)) in
                      try DateTime.FromText(t, [Format = "dd/MM/yyyy HH:mm", Culture = "de-DE"])
                      otherwise try DateTime.FromText(t, [Format = "yyyy.MM.dd-HH:mm", Culture = "de-DE"])
                      otherwise null,                    // "unbekannt" und reine Datumswerte -> null
    Arrival  = Table.TransformColumns(AirFix, {{"CargoArrivalTime", ParseDT, type datetime}}),
    Types    = Table.TransformColumnTypes(Arrival, {
                  {"ProcessingStart", type datetime}, {"ProcessingEnd", type datetime},
                  {"ShipmentDate", type date}, {"Weight_kg", type number}, {"Volume_m3", type number},
                  {"NumPackages", Int64.Type}, {"NumEmployeesShift", Int64.Type}, {"IncidentFlag", type logical}}),

    // 3) Duplikate: vollständigste Zeile pro AWB behalten (Sortieren + Buffer + Distinct)
    Rank     = Table.AddColumn(Types, "_hasArr", each if [CargoArrivalTime] = null then 0 else 1, Int64.Type),
    Sorted   = Table.Buffer(Table.Sort(Rank, {{"AWB_Number", Order.Ascending}, {"_hasArr", Order.Descending}})),
    NoDups   = Table.RemoveColumns(Table.Distinct(Sorted, {"AWB_Number"}), {"_hasArr"}),

    // 4) Unplausible Werte -> null (nicht löschen, nicht raten)
    Weight   = Table.TransformColumns(NoDups, {{"Weight_kg",
                  each if _ = null or _ <= 0 or _ > 10000 then null else _, type number}}),
    Pack     = Table.TransformColumns(Weight, {{"NumPackages", each if _ = 0 then null else _, Int64.Type}}),

    // 5) Dauern in Minuten; negative Dauern -> null
    Wait     = Table.AddColumn(Pack, "WaitTime_min",
                  each let m = Duration.TotalMinutes([ProcessingStart] - [CargoArrivalTime])
                       in if m <> null and m < 0 then null else m, type number),
    Proc     = Table.AddColumn(Wait, "ProcessingTime_min",
                  each let m = Duration.TotalMinutes([ProcessingEnd] - [ProcessingStart])
                       in if m <> null and m < 0 then null else m, type number),

    // 6) Mit Flights verbinden (Left Outer) und Puffer berechnen
    Merged   = Table.NestedJoin(Proc, {"FlightID"}, Flights, {"FlightID"}, "F", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Merged, "F", {"ScheduledDeparture", "ActualDeparture", "Destination"}),
    Buffer   = Table.AddColumn(Expanded, "Buffer_min",
                  each Duration.TotalMinutes([ScheduledDeparture] - [ProcessingEnd]), type number),
    Flag     = Table.AddColumn(Buffer, "Incomplete_End",
                  each if [ProcessingEnd] = null and [Status] = "Abgeschlossen" then 1 else 0, Int64.Type)
in
    Flag
