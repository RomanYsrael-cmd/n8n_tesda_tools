from __future__ import annotations

import json
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

from .schemas import JobStatus

FOLDERS = {
    JobStatus.INBOX: "Inbox",
    JobStatus.NORMALIZING: "Inbox",
    JobStatus.REVIEW: "Inbox",
    JobStatus.APPROVED: "In Progress",
    JobStatus.GENERATING: "In Progress",
    JobStatus.PAUSED: "In Progress",
    JobStatus.FAILED: "In Progress",
    JobStatus.CANCELLED: "In Progress",
    JobStatus.SUCCESS: "Success",
    JobStatus.FINISHED: "Finished",
}


def ensure_layout(root: Path) -> None:
    for name in ["Inbox", "In Progress", "Success", "Finished", "JSON Dump/Success", "JSON Dump/Failed"]:
        (root / name).mkdir(parents=True, exist_ok=True)


def sanitize_filename(name: str, suffix: str = ".docx") -> str:
    stem = Path(name).stem
    stem = unicodedata.normalize("NFKC", stem)
    stem = re.sub(r"[^\w .()-]", "_", stem, flags=re.UNICODE)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")[:100] or "syllabus"
    return stem + suffix


def safe_module_filename(week: int, lesson: int, title: str) -> str:
    clean = sanitize_filename(title, "")[:70] or "Module"
    return f"Week {week:02d} - Lesson {lesson:02d} - {clean}.docx"


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def job_dir(root: Path, job_id: str, status: JobStatus) -> Path:
    return root / FOLDERS[status] / job_id


def transition(root: Path, job_id: str, old: JobStatus, new: JobStatus) -> Path:
    source = job_dir(root, job_id, old)
    target = job_dir(root, job_id, new)
    if source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f"Target job folder already exists: {target}")
        shutil.move(str(source), str(target))
    return target


def dump_json(root: Path, success: bool, name: str, payload: object) -> Path:
    folder = root / "JSON Dump" / ("Success" if success else "Failed")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{sanitize_filename(name, '')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path

