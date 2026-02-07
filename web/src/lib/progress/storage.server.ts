import "server-only";

import fs from "node:fs";
import path from "node:path";

import type { OverridesData, ProgressDataBase } from "./types";
import { OverridesDataSchema, ProgressDataSchema } from "./schema";

const dataDir = () => path.join(process.cwd(), "data");

export function readBaseData(): ProgressDataBase {
  const basePath = path.join(dataDir(), "base.json");
  const raw = fs.readFileSync(basePath, "utf8");
  return ProgressDataSchema.parse(JSON.parse(raw));
}

export function readAutoOverridesData(): OverridesData {
  const autoPath = path.join(dataDir(), "auto_overrides.json");
  if (!fs.existsSync(autoPath)) {
    return {
      version: "0.1",
      updatedAt: new Date(0).toISOString(),
      nodes: {},
    };
  }
  const raw = fs.readFileSync(autoPath, "utf8");
  return OverridesDataSchema.parse(JSON.parse(raw));
}

export function readOverridesData(): OverridesData {
  const overridesPath = path.join(dataDir(), "overrides.json");
  if (!fs.existsSync(overridesPath)) {
    return {
      version: "0.1",
      updatedAt: new Date(0).toISOString(),
      nodes: {},
    };
  }
  const raw = fs.readFileSync(overridesPath, "utf8");
  return OverridesDataSchema.parse(JSON.parse(raw));
}

export function writeOverridesData(next: OverridesData) {
  const overridesPath = path.join(dataDir(), "overrides.json");
  fs.mkdirSync(path.dirname(overridesPath), { recursive: true });
  fs.writeFileSync(overridesPath, JSON.stringify(next, null, 2) + "\n", "utf8");
}
