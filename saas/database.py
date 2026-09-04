from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


MIGRATION = """
CREATE TABLE IF NOT EXISTS saas_users (
  id BIGSERIAL PRIMARY KEY, firebase_uid TEXT UNIQUE NOT NULL, email TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'user', status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_login_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS saas_subscriptions (
  user_id BIGINT PRIMARY KEY REFERENCES saas_users(id) ON DELETE CASCADE,
  plan TEXT NOT NULL DEFAULT 'free', status TEXT NOT NULL DEFAULT 'active',
  paymongo_customer_id TEXT, paymongo_subscription_id TEXT, current_period_end TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS saas_jobs (
  id UUID PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES saas_users(id) ON DELETE CASCADE,
  tool TEXT NOT NULL CHECK (tool IN ('module','cblm')), filename TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued', stage TEXT NOT NULL DEFAULT 'upload', progress INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL DEFAULT '', input_key TEXT NOT NULL, output_key TEXT, error TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb, cancel_requested BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS saas_jobs_user_created ON saas_jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS saas_jobs_claim ON saas_jobs(status, created_at) WHERE status='queued';
CREATE TABLE IF NOT EXISTS saas_job_events (
  id BIGSERIAL PRIMARY KEY, job_id UUID NOT NULL REFERENCES saas_jobs(id) ON DELETE CASCADE,
  level TEXT NOT NULL DEFAULT 'info', stage TEXT NOT NULL, message TEXT NOT NULL,
  detail JSONB NOT NULL DEFAULT '{}'::jsonb, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saas_events_job_id ON saas_job_events(job_id, id);
CREATE TABLE IF NOT EXISTS saas_webhook_events (
  provider TEXT NOT NULL, external_id TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload JSONB NOT NULL, PRIMARY KEY(provider, external_id)
);
"""


class SaaSDatabase:
    def __init__(self, url: str):
        self.pool = ConnectionPool(url, min_size=1, max_size=12, kwargs={"row_factory": dict_row})

    @contextmanager
    def connection(self) -> Iterator[Any]:
        with self.pool.connection() as conn:
            yield conn

    def migrate(self) -> None:
        with self.connection() as conn:
            conn.execute(MIGRATION)

    def user_for_token(self, uid: str, email: str, name: str, admin_email: str) -> dict:
        role = "admin" if email.lower() == admin_email else "user"
        with self.connection() as conn:
            user = conn.execute("""
              INSERT INTO saas_users(firebase_uid,email,display_name,role) VALUES(%s,%s,%s,%s)
              ON CONFLICT(firebase_uid) DO UPDATE SET email=excluded.email, display_name=excluded.display_name,
                last_login_at=now() RETURNING *
            """, (uid, email.lower(), name or "", role)).fetchone()
            conn.execute("INSERT INTO saas_subscriptions(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (user["id"],))
            return user

    def jobs(self, user_id: int) -> list[dict]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM saas_jobs WHERE user_id=%s ORDER BY created_at DESC", (user_id,)).fetchall()

    def user_email(self, user_id: int) -> str:
        with self.connection() as conn:
            row = conn.execute("SELECT email FROM saas_users WHERE id=%s", (user_id,)).fetchone()
            return row["email"] if row else ""

    def job(self, job_id: str, user_id: int | None = None) -> dict | None:
        query, args = "SELECT * FROM saas_jobs WHERE id=%s", [job_id]
        if user_id is not None:
            query += " AND user_id=%s"; args.append(user_id)
        with self.connection() as conn:
            return conn.execute(query, args).fetchone()

    def create_job(self, job_id: str, user_id: int, tool: str, filename: str, key: str) -> None:
        with self.connection() as conn:
            conn.execute("INSERT INTO saas_jobs(id,user_id,tool,filename,input_key) VALUES(%s,%s,%s,%s,%s)",
                         (job_id, user_id, tool, filename, key))
            conn.execute("INSERT INTO saas_job_events(job_id,stage,message) VALUES(%s,'upload','Upload stored securely')", (job_id,))

    def events(self, job_id: str, after: int = 0) -> list[dict]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM saas_job_events WHERE job_id=%s AND id>%s ORDER BY id", (job_id, after)).fetchall()

    def cancel(self, job_id: str, user_id: int) -> bool:
        with self.connection() as conn:
            row = conn.execute("UPDATE saas_jobs SET cancel_requested=true,updated_at=now() WHERE id=%s AND user_id=%s AND status NOT IN ('success','failed','cancelled') RETURNING id", (job_id,user_id)).fetchone()
            return bool(row)

    def delete_job(self, job_id: str, user_id: int) -> bool:
        with self.connection() as conn:
            return bool(conn.execute("DELETE FROM saas_jobs WHERE id=%s AND user_id=%s RETURNING id",(job_id,user_id)).fetchone())

    def resume(self, job_id: str, user_id: int) -> bool:
        with self.connection() as conn:
            return bool(conn.execute("""UPDATE saas_jobs SET status='queued',cancel_requested=false,message='Queued to resume generation',updated_at=now()
              WHERE id=%s AND user_id=%s AND status IN ('paused','failed','cancelled') AND stage='generation' RETURNING id""",(job_id,user_id)).fetchone())

    def return_to_plan(self, job_id: str, user_id: int) -> bool:
        with self.connection() as conn:
            return bool(conn.execute("""UPDATE saas_jobs SET status='review',stage='planning',progress=25,cancel_requested=true,
              message='Returned to planning',error=NULL,updated_at=now() WHERE id=%s AND user_id=%s AND status NOT IN ('success','finished') RETURNING id""",(job_id,user_id)).fetchone())

    def claim(self) -> dict | None:
        with self.connection() as conn:
            return conn.execute("""
              UPDATE saas_jobs SET status='running',message=CASE WHEN stage='generation' THEN 'Generating documents' ELSE 'Reading syllabus' END,updated_at=now()
              WHERE id=(SELECT id FROM saas_jobs WHERE status='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
              RETURNING *
            """).fetchone()

    def approve(self, job_id: str, user_id: int, payload: dict) -> bool:
        with self.connection() as conn:
            row = conn.execute("""UPDATE saas_jobs SET status='queued',stage='generation',progress=25,
              message='Approved and queued for generation',payload=%s,updated_at=now()
              WHERE id=%s AND user_id=%s AND status='review' RETURNING id""",
              (json.dumps(payload), job_id, user_id)).fetchone()
            if row: conn.execute("INSERT INTO saas_job_events(job_id,stage,message) VALUES(%s,'generation','Plan approved; generation queued')", (job_id,))
            return bool(row)

    def save_plan(self, job_id: str, user_id: int, payload: dict) -> bool:
        with self.connection() as conn:
            row = conn.execute("""UPDATE saas_jobs SET payload=%s,message='Plan saved. Review it, then approve when ready.',updated_at=now()
              WHERE id=%s AND user_id=%s AND status='review' RETURNING id""",
              (json.dumps(payload), job_id, user_id)).fetchone()
            if row:
                conn.execute("INSERT INTO saas_job_events(job_id,stage,message) VALUES(%s,'review','Planning changes saved')", (job_id,))
            return bool(row)

    def update(self, job_id: str, **values: Any) -> None:
        allowed = {"status","stage","progress","message","output_key","error","payload","finished_at"}
        clean = {k: v for k,v in values.items() if k in allowed}
        if not clean: return
        parts, args = [], []
        for key, value in clean.items():
            parts.append(f"{key}=%s"); args.append(json.dumps(value) if key == "payload" else value)
        args.append(job_id)
        with self.connection() as conn:
            conn.execute(f"UPDATE saas_jobs SET {','.join(parts)},updated_at=now() WHERE id=%s", args)

    def event(self, job_id: str, stage: str, message: str, level: str="info", detail: dict | None=None) -> None:
        with self.connection() as conn:
            conn.execute("INSERT INTO saas_job_events(job_id,level,stage,message,detail) VALUES(%s,%s,%s,%s,%s)",
                         (job_id, level, stage, message, json.dumps(detail or {})))
