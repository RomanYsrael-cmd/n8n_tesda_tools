from __future__ import annotations

import json
import re
import shutil
import unicodedata
import uuid
from pathlib import Path

FOLDERS = {"inbox": "Inbox", "normalizing": "Inbox", "review": "Inbox", "approved": "In Progress", "generating": "In Progress", "paused": "In Progress", "failed": "In Progress", "success": "Success", "finished": "Finished"}


def ensure_layout(root: Path):
    for folder in ["Inbox", "In Progress", "Success", "Finished", "JSON Dump/Success", "JSON Dump/Failed"]:
        (root / folder).mkdir(parents=True, exist_ok=True)


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def safe_name(value: str, suffix: str = ".docx") -> str:
    stem = unicodedata.normalize("NFKC", Path(value).stem)
    stem = re.sub(r"[^\w .()-]", "_", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" ._")[:100] or "CBLM"
    return stem + suffix


def job_dir(root: Path, job_id: str, status: str) -> Path:
    return root / FOLDERS[status] / job_id


def transition(root: Path, job_id: str, old: str, new: str) -> Path:
    source, target = job_dir(root, job_id, old), job_dir(root, job_id, new)
    if source.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.move(str(source), str(target))
    return target


def dump(root: Path, success: bool, filename: str, value):
    folder = root / "JSON Dump" / ("Success" if success else "Failed")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / safe_name(filename, ".json")
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path

