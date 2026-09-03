from __future__ import annotations

import json
import sys
from pathlib import Path

from app.validation import render_verify

from .database import CBLMDatabase
from .documents import audit_docx, build_cblm, package_outputs
from .schemas import CBLMPlan
from .storage import job_dir


def rebuild(job_id: str, root: Path = Path("/data/CBLM Builder"), templates: Path = Path("/cblm/Templates")):
    db = CBLMDatabase(root / "cblm-builder.sqlite3")
    row = db.get_job(job_id)
    if not row or row["status"] not in {"success", "finished"}:
        raise ValueError("Only a completed CBLM job can be rebuilt")
    plan = CBLMPlan.model_validate_json(row["plan_json"])
    base = job_dir(root, job_id, row["status"])
    reports = []
    for outcome in plan.learning_outcomes:
        path = build_cblm(templates, base / "CBLMs", plan, outcome)
        audit = audit_docx(path)
        render = render_verify(path, base / "render" / f"lo-{outcome.number}")
        reports.append({"learning_outcome": outcome.number, "file": path.name, "audit": audit, "render": render})
        if not audit["valid"] or not render.get("valid"):
            raise ValueError(f"Rebuilt CBLM {outcome.number} failed validation")
    (base / "cblm-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    (base / "validation-report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    package_outputs(base)
    db.update_job(job_id, message="CBLMs rebuilt and validated", error=None)
    return reports


if __name__ == "__main__":
    rebuild(sys.argv[1])
