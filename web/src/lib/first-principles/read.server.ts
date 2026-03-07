import fs from "node:fs";
import path from "node:path";

import type { FirstPrinciplesData } from "./types";

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

export function readFirstPrinciplesData(): FirstPrinciplesData | null {
  const p = dataPath("first_principles_lens.json");
  if (!fs.existsSync(p)) return null;
  try {
    return JSON.parse(fs.readFileSync(p, "utf8")) as FirstPrinciplesData;
  } catch {
    return null;
  }
}
