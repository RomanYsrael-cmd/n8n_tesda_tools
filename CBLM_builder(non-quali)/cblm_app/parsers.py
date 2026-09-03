from __future__ import annotations

import re
from dataclasses import dataclass


def clean_response(value: str) -> str:
    text = value.strip().lstrip("\ufeff")
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _heading(line: str) -> str:
    value = re.sub(r"^#{1,6}\s*", "", line.strip())
    value = re.sub(r"^\d+[.)]\s*", "", value)
    return value.strip(" *_`:.-").casefold()


@dataclass
class SelfCheck:
    quiz_instructions: str
    quiz: str
    answer_key: str


def parse_self_check(value: str) -> SelfCheck:
    text = clean_response(value)
    lines = text.splitlines()
    answer_at = next((index for index, line in enumerate(lines) if _heading(line) in {"answer key", "answers", "key"}), -1)
    if answer_at < 0:
        raise ValueError("Self-Check response is missing an Answer Key heading")
    question_lines = lines[:answer_at]
    answer_lines = lines[answer_at + 1:]
    while question_lines and _heading(question_lines[0]) in {"self-check", "self check", "quiz", "questions"}:
        question_lines.pop(0)
    instructions = []
    while question_lines:
        line = question_lines[0].strip()
        if not line:
            question_lines.pop(0)
            continue
        if re.match(r"^(?:directions?|instructions?)\s*:", line, re.I):
            instructions.append(re.sub(r"^(?:directions?|instructions?)\s*:\s*", "", line, flags=re.I))
            question_lines.pop(0)
            continue
        if _heading(line) in {"multiple choice", "true or false", "identification", "matching type", "sequencing", "short answer", "enumeration", "situational", "case-based questions"}:
            instructions.append(line.strip())
            question_lines.pop(0)
            continue
        break
    quiz = "\n".join(question_lines).strip()
    answer_key = "\n".join(answer_lines).strip()
    if not quiz:
        raise ValueError("Self-Check response contains no questions")
    if not answer_key:
        raise ValueError("Self-Check response contains no answers")
    question_markers = len(re.findall(r"(?m)^\s*\d+[.)]\s+", quiz))
    answer_markers = len(re.findall(r"(?m)^\s*\d+[.)]\s+", answer_key))
    if question_markers and answer_markers and answer_markers < question_markers:
        raise ValueError(f"Answer Key has {answer_markers} entries for {question_markers} numbered questions")
    return SelfCheck("\n".join(instructions).strip() or "Answer the following questions.", quiz, answer_key)


@dataclass
class TaskSheet:
    activity_title: str
    activity_objectives: str
    activity_supplies: str
    activity_equipment: str
    activity_steps: str
    activity_method: str
    activity_criteria: list[str]


TASK_ALIASES = {
    "title of task sheet": "title",
    "task sheet title": "title",
    "title": "title",
    "performance objective": "objective",
    "supplies/materials": "supplies",
    "supplies and materials": "supplies",
    "list of supplies": "supplies",
    "equipment": "equipment",
    "list of equipment": "equipment",
    "steps/procedure": "steps",
    "steps": "steps",
    "procedure": "steps",
    "assessment method": "method",
    "performance criteria": "criteria",
    "performance criteria checklist": "criteria",
}


def parse_task_sheet(value: str) -> TaskSheet:
    text = clean_response(value)
    sections = {name: [] for name in {"title", "objective", "supplies", "equipment", "steps", "method", "criteria"}}
    current = None
    pending_title = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        normalized = _heading(line)
        if normalized in {"task sheet", "task-sheet"}:
            pending_title = True
            current = None
            continue
        # Smaller/local models commonly put the activity title directly below
        # TASK SHEET without repeating the requested title label. This is an
        # unambiguous structural variation and is safe to normalize in Python.
        if pending_title and normalized not in TASK_ALIASES:
            sections["title"].append(line.strip("*_# "))
            pending_title = False
            continue
        if normalized in {"critical criteria", "task difficulty", "realistic workplace context", "workplace context", "notes", "trainer notes"}:
            current = None
            continue
        matched = None
        remainder = ""
        for label, key in sorted(TASK_ALIASES.items(), key=lambda pair: len(pair[0]), reverse=True):
            match = re.match(rf"^{re.escape(label)}\s*(?::|[-–—])?\s*(.*)$", normalized, re.I)
            if match:
                matched = key
                original_match = re.match(rf"^(?:#+\s*)?(?:\d+[.)]\s*)?{re.escape(label)}\s*(?::|[-–—])?\s*(.*)$", line, re.I)
                remainder = original_match.group(1).strip() if original_match else ""
                break
        if matched:
            pending_title = False
            current = matched
            if remainder:
                sections[current].append(remainder)
        elif current:
            sections[current].append(line)
    missing = [key for key in ["title", "objective", "supplies", "equipment", "steps", "method", "criteria"] if not sections[key]]
    if missing:
        raise ValueError("Task Sheet is missing: " + ", ".join(missing))
    criteria = []
    for line in sections["criteria"]:
        item = line.strip()
        if item.startswith("|") and item.endswith("|"):
            cells = [cell.strip() for cell in item.strip("|").split("|")]
            if not cells or cells[0].casefold() == "performance criteria" or re.fullmatch(r":?-{3,}:?", cells[0]):
                continue
            item = cells[0]
        item = re.sub(r"^(?:[-*+•]\s+|\d+[.)]\s+)", "", item).strip()
        if item and item not in criteria:
            criteria.append(item)
    if not criteria:
        raise ValueError("Task Sheet has no performance criteria")
    return TaskSheet(
        activity_title=" ".join(sections["title"]),
        activity_objectives=" ".join(sections["objective"]),
        activity_supplies="\n".join(sections["supplies"]),
        activity_equipment="\n".join(sections["equipment"]),
        activity_steps="\n".join(sections["steps"]),
        activity_method="\n".join(sections["method"]),
        activity_criteria=criteria,
    )
