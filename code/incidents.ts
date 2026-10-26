// Incident-Erkennung für den Workflow "kritische Verzögerung" (reine Funktionen, leicht testbar)
export type Priority = "Critical" | "Express" | "Standard";

export interface Shipment {
  awb: string;
  warehouse: string;
  shift: "Früh" | "Spät" | "Nacht";
  priority: Priority;
  cargoType: string;
  bufferMin: number | null;      // ScheduledDeparture - ProcessingEnd (null = noch nicht fertig/unbekannt)
  processingMin: number | null;
  status: string;
}

export interface Incident {
  awb: string;
  severity: "kritisch" | "hoch";
  reason: string;
  owner: string;                 // Verantwortliche Rolle, nicht Person
}

const SLA_BUFFER: Record<Priority, number> = { Critical: 120, Express: 90, Standard: 60 };
const OWNER_BY_SHIFT: Record<Shipment["shift"], string> = {
  Früh: "Schichtleiter Früh", Spät: "Schichtleiter Spät", Nacht: "Schichtleiter Nacht",
};

export function detectIncident(s: Shipment, procP95Min = 65): Incident | null {
  if (s.status === "Abgebrochen") return null;
  const limit = SLA_BUFFER[s.priority];
  if (s.bufferMin !== null && s.bufferMin < 0) {
    return { awb: s.awb, severity: "kritisch", owner: OWNER_BY_SHIFT[s.shift],
             reason: `Nach geplantem Abflug fertig (${Math.round(s.bufferMin)} min)` };
  }
  if (s.bufferMin !== null && s.bufferMin < limit) {
    return { awb: s.awb, severity: s.priority === "Critical" ? "kritisch" : "hoch", owner: OWNER_BY_SHIFT[s.shift],
             reason: `SLA-Puffer ${Math.round(s.bufferMin)} min < ${limit} min (${s.priority})` };
  }
  if (s.processingMin !== null && s.processingMin > procP95Min && s.priority !== "Standard") {
    return { awb: s.awb, severity: "hoch", owner: OWNER_BY_SHIFT[s.shift],
             reason: `Bearbeitung ${Math.round(s.processingMin)} min > P95 (${procP95Min} min)` };
  }
  return null;
}

// Nachricht für Teams / Power Automate (Adaptive-Card-Text; JSON, das ein HTTP-Trigger annimmt)
export function toTeamsPayload(i: Incident): { title: string; text: string; formUrl: string } {
  return {
    title: `[${i.severity.toUpperCase()}] Sendung ${i.awb}`,
    text: `${i.reason}. Verantwortlich: ${i.owner}. Bitte Ursache im Formular erfassen.`,
    formUrl: `https://forms.office.com/r/EXAMPLE?awb=${encodeURIComponent(i.awb)}`,
  };
}
