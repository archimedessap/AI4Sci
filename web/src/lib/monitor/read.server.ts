import fs from "node:fs";
import path from "node:path";

import type { MonitorStatusData } from "./types";

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

export function readMonitorStatus(): MonitorStatusData | null {
  const p = dataPath("monitor_status.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as MonitorStatusData;
  } catch {
    return null;
  }
}
