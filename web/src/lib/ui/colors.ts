import type { MaturityLevel } from "@/lib/progress/types";

export function maturityColor(level: MaturityLevel) {
  switch (level) {
    case 0:
      return "#475569"; // slate-600
    case 1:
      return "#22d3ee"; // cyan-400
    case 2:
      return "#4ade80"; // green-400
    case 3:
      return "#a78bfa"; // violet-400
    case 4:
      return "#fb7185"; // rose-400
    default:
      return "#64748b";
  }
}

export function maturityLabel(level: MaturityLevel) {
  switch (level) {
    case 0:
      return "0 • None";
    case 1:
      return "1 • Assist";
    case 2:
      return "2 • Competitive";
    case 3:
      return "3 • Co‑Scientist";
    case 4:
      return "4 • Closed‑Loop";
    default:
      return `${level}`;
  }
}

