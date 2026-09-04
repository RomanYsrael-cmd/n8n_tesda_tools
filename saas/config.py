from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SaaSConfig:
    public_url: str
    admin_email: str
    session_secret: str
    firebase_project_id: str
    firebase_web_api_key: str
    firebase_service_account_path: str
    firebase_vapid_key: str
    database_url: str
    r2_endpoint: str
    r2_bucket: str
    r2_access_key: str
    r2_secret_key: str
    paymongo_public_key: str
    paymongo_secret_key: str
    paymongo_webhook_secret: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    from_email: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str


def load_config() -> SaaSConfig:
    path = Path(os.getenv("TESDA_SAAS_CONFIG", "/run/secrets/saas.json"))
    if not path.is_file():
        raise RuntimeError(f"SaaS configuration is missing: {path}")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    app, firebase, pg, r2 = raw["application"], raw["firebase"], raw["postgres"], raw["r2"]
    paymongo, email, llm = raw["paymongo"], raw["email"], raw.get("platform_llm", {})
    required = {
        "application.public_base_url": app.get("public_base_url"),
        "application.session_secret": app.get("session_secret"),
        "firebase.project_id": firebase.get("project_id"),
        "firebase.service_account_json_path": firebase.get("service_account_json_path"),
        "postgres.database_url": os.getenv("TESDA_DATABASE_URL", pg.get("database_url")),
        "r2.bucket": r2.get("bucket"),
        "r2.access_key_id": r2.get("access_key_id"),
        "r2.secret_access_key": r2.get("secret_access_key"),
    }
    missing = [name for name, value in required.items() if not value or value == "later"]
    if missing:
        raise RuntimeError("Incomplete SaaS configuration: " + ", ".join(missing))
    return SaaSConfig(
        public_url=app["public_base_url"].rstrip("/"), admin_email=app["admin_email"].lower(),
        session_secret=app["session_secret"], firebase_project_id=firebase["project_id"],
        firebase_web_api_key=firebase.get("web_api_key", ""),
        firebase_service_account_path=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", firebase["service_account_json_path"]),
        firebase_vapid_key=firebase.get("web_push_vapid_public_key", ""),
        database_url=os.getenv("TESDA_DATABASE_URL", pg["database_url"]),
        r2_endpoint=f"https://{r2['account_id']}.r2.cloudflarestorage.com", r2_bucket=r2["bucket"],
        r2_access_key=r2["access_key_id"], r2_secret_key=r2["secret_access_key"],
        paymongo_public_key=paymongo.get("public_key", ""), paymongo_secret_key=paymongo.get("secret_key", ""),
        paymongo_webhook_secret=paymongo.get("webhook_secret", ""), smtp_host=email["smtp_host"],
        smtp_port=int(email.get("smtp_port", 465)), smtp_username=email["smtp_username"],
        smtp_password=email["smtp_password"], from_email=email["from_email"],
        llm_base_url=llm.get("base_url", ""), llm_model=llm.get("model", ""), llm_api_key=llm.get("api_key", ""),
    )
