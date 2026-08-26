import json

from app.config import Settings
from app.database import Database
from app.extraction import extract_syllabus
from app.schemas import JobStatus
from app.services import build_imported
from app.storage import ensure_layout, job_dir
from conftest import SYLLABUS, TEMPLATE, make_bundle


def test_ae17_manual_mock_smoke(tmp_path):
    root = tmp_path / "data"; ensure_layout(root)
    db = Database(root / "db.sqlite3"); db.migrate(); db.create_job("ae17test", SYLLABUS.name)
    inbox = job_dir(root, "ae17test", JobStatus.INBOX); inbox.mkdir()
    plan = extract_syllabus(SYLLABUS)
    db.update_job("ae17test", status=JobStatus.REVIEW, normalized_json=plan.model_dump_json())
    modules = [make_bundle(w.actual_week, w.lesson_number, w.topic_scope).model_dump() for w in plan.weeks if w.generate]
    config = Settings(data_root=root, template=TEMPLATE).resolved()
    ok, errors = build_imported(config, db, "ae17test", {"modules": modules})
    assert ok, errors
    success = job_dir(root, "ae17test", JobStatus.SUCCESS)
    assert len(list((success / "modules").glob("*.docx"))) == 13
    assert (success / "course-modules.zip").exists()
    assert json.loads((success / "generation-report.json").read_text())["llm_generation_calls"] == 0

