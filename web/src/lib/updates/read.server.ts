import fs from "node:fs";
import path from "node:path";

import type { DailyUpdatesData } from "@/lib/updates/types";

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

export function readDailyUpdates(): DailyUpdatesData | null {
  const p = dataPath("daily_updates.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as DailyUpdatesData;
  } catch {
    return null;
  }
}

