import "server-only";

import fs from "node:fs";
import path from "node:path";

export type CatalogDomain = {
  id: string;
  name: string;
  count: number;
};

export type CatalogMethod = {
  tag: string;
  label: string;
  description?: string | null;
  count: number;
};

export type CatalogPaper = {
  id: string;
  doi?: string | null;
  arxivId?: string | null;
  title: string;
  abstract?: string | null;
  publicationYear?: number | null;
  publicationDate?: string | null;
  citedBy?: number | null;
  url?: string | null;
  source?: string | null;
  domains?: string[];
  methodTags?: string[];
};

export type PapersCatalog = {
  version: string;
  generatedAt: string;
  db?: { path?: string; papers?: number; links?: number };
  domains?: CatalogDomain[];
  methods?: CatalogMethod[];
  papers?: CatalogPaper[];
};

let cached: PapersCatalog | null = null;
let cachedMtimeMs = 0;

function dataPath(filename: string) {
  return path.join(process.cwd(), "data", filename);
}

export function readPapersCatalog(): PapersCatalog | null {
  const p = dataPath("papers_catalog.json");
  if (!fs.existsSync(p)) return null;
  try {
    const stat = fs.statSync(p);
    const mtimeMs = stat.mtimeMs || 0;
    if (cached && cachedMtimeMs === mtimeMs) return cached;
    const raw = fs.readFileSync(p, "utf8");
    cached = JSON.parse(raw) as PapersCatalog;
    cachedMtimeMs = mtimeMs;
    return cached;
  } catch {
    return null;
  }
}

