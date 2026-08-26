import json

from app.database import Database
from app.prompts import master_prompt, repair_prompt
from app.schemas import JobStatus
from app.storage import ensure_layout, job_dir, transition
from app.extraction import extract_syllabus
from conftest import SYLLABUS


def test_folder_transition(tmp_path):
    ensure_layout(tmp_path)
    source = job_dir(tmp_path, "abc", JobStatus.INBOX)
    source.mkdir()
    (source / "keep.txt").write_text("partial")
    target = transition(tmp_path, "abc", JobStatus.INBOX, JobStatus.APPROVED)
    assert (target / "keep.txt").read_text() == "partial"
    assert not source.exists()


def test_pause_resume_control_survives_database_restart(tmp_path):
    db = Database(tmp_path / "state.sqlite3"); db.migrate(); db.create_job("abc", "test.docx")
    db.set_control("abc", pause=True, cancel=False)
    reopened = Database(tmp_path / "state.sqlite3"); reopened.migrate()
    assert json.loads(reopened.get_job("abc")["control_json"])["pause"] is True
    reopened.set_control("abc", pause=False)
    assert json.loads(reopened.get_job("abc")["control_json"])["pause"] is False


def test_prompt_generation_is_deterministic_and_safe():
    plan = extract_syllabus(SYLLABUS)
    first = master_prompt(plan)
    assert first == master_prompt(plan)
    assert "untrusted reference material" in first
    repair = repair_prompt(["quiz: wrong count"], {"bad": True})
    assert "quiz: wrong count" in repair and '"bad": true' in repair

