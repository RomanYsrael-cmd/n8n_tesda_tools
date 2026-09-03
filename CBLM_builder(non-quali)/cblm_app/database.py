from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


class CBLMDatabase:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def migrate(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL,
              progress INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
              plan_json TEXT, control_json TEXT NOT NULL DEFAULT '{}', error TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stages (
              job_id TEXT NOT NULL, lo_number INTEGER NOT NULL, topic_number INTEGER NOT NULL,
              stage TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              message TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
              PRIMARY KEY(job_id,lo_number,topic_number,stage),
              FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            """)
            con.execute("UPDATE jobs SET status='paused', message='Generation was interrupted. Resume when ready.' WHERE status='generating'")

    def create_job(self, job_id: str, filename: str):
        now = self.now()
        with self.connect() as con:
            con.execute("INSERT INTO jobs(id,filename,status,created_at,updated_at) VALUES(?,?,?,?,?)", (job_id, filename, "inbox", now, now))

    def update_job(self, job_id: str, **values):
        values["updated_at"] = self.now()
        keys = list(values)
        with self.connect() as con:
            con.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in keys)} WHERE id=?", [values[k] for k in keys] + [job_id])

    def get_job(self, job_id: str):
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def delete_job(self, job_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def set_control(self, job_id: str, **values):
        row = self.get_job(job_id)
        current = json.loads(row["control_json"] or "{}")
        current.update(values)
        self.update_job(job_id, control_json=json.dumps(current))

    def upsert_stage(self, job_id: str, lo: int, topic: int, stage: str, status: str, message: str = "", increment: bool = False):
        now = self.now()
        with self.connect() as con:
            con.execute("""
            INSERT INTO stages(job_id,lo_number,topic_number,stage,status,attempts,message,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id,lo_number,topic_number,stage) DO UPDATE SET
            status=excluded.status,attempts=stages.attempts+?,message=excluded.message,updated_at=excluded.updated_at
            """, (job_id, lo, topic, stage, status, int(increment), message, now, int(increment)))

    def stages(self, job_id: str):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM stages WHERE job_id=? ORDER BY lo_number,topic_number,stage", (job_id,)).fetchall()
        return [dict(row) for row in rows]

    def clear_stages(self, job_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM stages WHERE job_id=?", (job_id,))

