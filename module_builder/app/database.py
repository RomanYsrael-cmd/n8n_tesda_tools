from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .schemas import JobStatus


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def migrate(self):
        with self.connect() as con:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
              id TEXT PRIMARY KEY, filename TEXT NOT NULL, status TEXT NOT NULL, mode TEXT,
              progress INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
              normalized_json TEXT, control_json TEXT NOT NULL DEFAULT '{}', error TEXT,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS stages (
              job_id TEXT NOT NULL, lesson_number INTEGER NOT NULL, actual_week INTEGER NOT NULL,
              stage TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
              message TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
              PRIMARY KEY(job_id, lesson_number, stage), FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            """)

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    def create_job(self, job_id: str, filename: str):
        now = self.now()
        with self.connect() as con:
            con.execute("INSERT INTO jobs(id,filename,status,created_at,updated_at) VALUES(?,?,?,?,?)", (job_id, filename, JobStatus.INBOX, now, now))

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
        return [dict(r) for r in rows]

    def set_control(self, job_id: str, **control):
        row = self.get_job(job_id)
        current = json.loads(row["control_json"] or "{}")
        current.update(control)
        self.update_job(job_id, control_json=json.dumps(current))

    def upsert_stage(self, job_id: str, lesson: int, week: int, stage: str, status: str, message: str = "", increment: bool = False):
        now = self.now()
        with self.connect() as con:
            con.execute("""
            INSERT INTO stages(job_id,lesson_number,actual_week,stage,status,attempts,message,updated_at)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id,lesson_number,stage) DO UPDATE SET
            status=excluded.status, attempts=stages.attempts+?, message=excluded.message, updated_at=excluded.updated_at
            """, (job_id, lesson, week, stage, status, int(increment), message, now, int(increment)))

    def stages(self, job_id: str):
        with self.connect() as con:
            rows = con.execute("SELECT * FROM stages WHERE job_id=? ORDER BY lesson_number,stage", (job_id,)).fetchall()
        return [dict(r) for r in rows]

    def clear_module_stages(self, job_id: str, lesson_number: int):
        with self.connect() as con:
            con.execute("DELETE FROM stages WHERE job_id=? AND lesson_number=?", (job_id, lesson_number))

    def clear_stages(self, job_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM stages WHERE job_id=?", (job_id,))

    def delete_job(self, job_id: str):
        with self.connect() as con:
            con.execute("DELETE FROM jobs WHERE id=?", (job_id,))

    def recover_interrupted(self):
        """Convert abandoned in-memory work into explicit resumable states on startup."""
        with self.connect() as con:
            con.execute(
                "UPDATE jobs SET status=?, message=?, updated_at=? WHERE status=?",
                (JobStatus.REVIEW, "Normalization was interrupted; upload remains safe. Retry normalization.", self.now(), JobStatus.NORMALIZING),
            )
            con.execute(
                "UPDATE jobs SET status=?, message=?, updated_at=? WHERE status=?",
                (JobStatus.PAUSED, "Generation was interrupted by a restart. Choose Resume to continue.", self.now(), JobStatus.GENERATING),
            )

    def set_setting(self, key: str, value: str):
        with self.connect() as con:
            con.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, value, self.now()))

    def get_setting(self, key: str):
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None
