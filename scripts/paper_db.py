from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con


def init_db(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS papers (
          openalex_id TEXT PRIMARY KEY,
          doi TEXT,
          arxiv_id TEXT,
          title TEXT NOT NULL,
          abstract TEXT,
          publication_date TEXT,
          publication_year INTEGER,
          cited_by_count INTEGER,
          primary_url TEXT,
          source TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_papers_year ON papers(publication_year);
        CREATE INDEX IF NOT EXISTS idx_papers_cited ON papers(cited_by_count);

        CREATE TABLE IF NOT EXISTS paper_domains (
          openalex_id TEXT NOT NULL,
          domain_id TEXT NOT NULL,
          domain_concept_id TEXT,
          PRIMARY KEY (openalex_id, domain_id),
          FOREIGN KEY (openalex_id) REFERENCES papers(openalex_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paper_domains_domain ON paper_domains(domain_id);

        -- OpenAlex concepts attached to works (used for subfield + method tagging).
        CREATE TABLE IF NOT EXISTS concepts (
          concept_id TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          level INTEGER,
          wikidata TEXT,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_concepts_level ON concepts(level);

        CREATE TABLE IF NOT EXISTS paper_concepts (
          openalex_id TEXT NOT NULL,
          concept_id TEXT NOT NULL,
          score REAL,
          PRIMARY KEY (openalex_id, concept_id),
          FOREIGN KEY (openalex_id) REFERENCES papers(openalex_id) ON DELETE CASCADE,
          FOREIGN KEY (concept_id) REFERENCES concepts(concept_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paper_concepts_concept ON paper_concepts(concept_id);
        CREATE INDEX IF NOT EXISTS idx_paper_concepts_paper ON paper_concepts(openalex_id);

        -- Generic tagging system (methods, subfields, etc).
        CREATE TABLE IF NOT EXISTS tag_defs (
          tag_type TEXT NOT NULL,
          tag TEXT NOT NULL,
          label TEXT,
          description TEXT,
          PRIMARY KEY (tag_type, tag)
        );

        CREATE TABLE IF NOT EXISTS paper_tags (
          openalex_id TEXT NOT NULL,
          tag_type TEXT NOT NULL,
          tag TEXT NOT NULL,
          confidence REAL,
          source TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (openalex_id, tag_type, tag),
          FOREIGN KEY (openalex_id) REFERENCES papers(openalex_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_paper_tags_type ON paper_tags(tag_type);
        CREATE INDEX IF NOT EXISTS idx_paper_tags_tag ON paper_tags(tag);

        CREATE TABLE IF NOT EXISTS sync_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          started_at TEXT NOT NULL,
          finished_at TEXT,
          source TEXT NOT NULL,
          params_json TEXT NOT NULL,
          added INTEGER NOT NULL DEFAULT 0,
          updated INTEGER NOT NULL DEFAULT 0,
          errors INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    con.commit()


def upsert_paper(con: sqlite3.Connection, paper: dict[str, Any]) -> str:
    """
    Returns: "inserted" | "updated"
    """
    existed = (
        con.execute(
            "SELECT 1 FROM papers WHERE openalex_id = ? LIMIT 1",
            (paper["openalex_id"],),
        ).fetchone()
        is not None
    )

    con.execute(
        """
        INSERT INTO papers(
          openalex_id, doi, arxiv_id, title, abstract, publication_date, publication_year,
          cited_by_count, primary_url, source, created_at, updated_at
        )
        VALUES(
          :openalex_id, :doi, :arxiv_id, :title, :abstract, :publication_date, :publication_year,
          :cited_by_count, :primary_url, :source, :created_at, :updated_at
        )
        ON CONFLICT(openalex_id) DO UPDATE SET
          doi=excluded.doi,
          arxiv_id=excluded.arxiv_id,
          title=excluded.title,
          abstract=COALESCE(excluded.abstract, papers.abstract),
          publication_date=COALESCE(excluded.publication_date, papers.publication_date),
          publication_year=COALESCE(excluded.publication_year, papers.publication_year),
          cited_by_count=COALESCE(excluded.cited_by_count, papers.cited_by_count),
          primary_url=COALESCE(excluded.primary_url, papers.primary_url),
          source=COALESCE(excluded.source, papers.source),
          updated_at=excluded.updated_at
        ;
        """,
        paper,
    )
    return "updated" if existed else "inserted"


def add_paper_domain(
    con: sqlite3.Connection,
    *,
    openalex_id: str,
    domain_id: str,
    domain_concept_id: str | None,
) -> None:
    con.execute(
        """
        INSERT OR IGNORE INTO paper_domains(openalex_id, domain_id, domain_concept_id)
        VALUES(?, ?, ?);
        """,
        (openalex_id, domain_id, domain_concept_id),
    )


def upsert_concept(con: sqlite3.Connection, concept: dict[str, Any]) -> None:
    con.execute(
        """
        INSERT INTO concepts(concept_id, display_name, level, wikidata, updated_at)
        VALUES(:concept_id, :display_name, :level, :wikidata, :updated_at)
        ON CONFLICT(concept_id) DO UPDATE SET
          display_name=excluded.display_name,
          level=COALESCE(excluded.level, concepts.level),
          wikidata=COALESCE(excluded.wikidata, concepts.wikidata),
          updated_at=excluded.updated_at
        ;
        """,
        concept,
    )


def replace_paper_concepts(
    con: sqlite3.Connection,
    *,
    openalex_id: str,
    concepts: list[dict[str, Any]],
) -> None:
    con.execute("DELETE FROM paper_concepts WHERE openalex_id = ?;", (openalex_id,))
    if not concepts:
        return
    con.executemany(
        """
        INSERT OR REPLACE INTO paper_concepts(openalex_id, concept_id, score)
        VALUES(:openalex_id, :concept_id, :score);
        """,
        concepts,
    )


def upsert_tag_def(
    con: sqlite3.Connection,
    *,
    tag_type: str,
    tag: str,
    label: str | None = None,
    description: str | None = None,
) -> None:
    con.execute(
        """
        INSERT INTO tag_defs(tag_type, tag, label, description)
        VALUES(?, ?, ?, ?)
        ON CONFLICT(tag_type, tag) DO UPDATE SET
          label=COALESCE(excluded.label, tag_defs.label),
          description=COALESCE(excluded.description, tag_defs.description)
        ;
        """,
        (tag_type, tag, label, description),
    )


def set_paper_tag(
    con: sqlite3.Connection,
    *,
    openalex_id: str,
    tag_type: str,
    tag: str,
    confidence: float | None,
    source: str,
    updated_at: str,
) -> None:
    con.execute(
        """
        INSERT INTO paper_tags(openalex_id, tag_type, tag, confidence, source, updated_at)
        VALUES(?, ?, ?, ?, ?, ?)
        ON CONFLICT(openalex_id, tag_type, tag) DO UPDATE SET
          confidence=COALESCE(excluded.confidence, paper_tags.confidence),
          source=excluded.source,
          updated_at=excluded.updated_at
        ;
        """,
        (openalex_id, tag_type, tag, confidence, source, updated_at),
    )


def clear_paper_tags(
    con: sqlite3.Connection,
    *,
    openalex_id: str,
    tag_type: str,
) -> None:
    con.execute(
        "DELETE FROM paper_tags WHERE openalex_id = ? AND tag_type = ?;",
        (openalex_id, tag_type),
    )
