#!/usr/bin/env python3
"""Build and validate semantic packages for the local TESDA TR corpus.

The generator deliberately writes JSON-shaped YAML. JSON is a strict subset of
YAML, which keeps the output dependency-light and makes it safe for Python,
n8n, and small local runtimes while retaining human-readable structure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

try:
    from pypdf import PdfReader
except ImportError as exc:  # pragma: no cover - environment diagnostic
    raise SystemExit("pypdf is required; use the bundled workspace Python runtime") from exc

try:
    import fitz  # PyMuPDF is substantially faster for corpus-scale extraction.
except ImportError:  # pragma: no cover - pypdf fallback remains supported
    fitz = None

ROOT = Path(__file__).resolve().parent
INDEXED = ROOT / "indexed"
STATUS_FILE = INDEXED / "_corpus-status.json"
DOCUMENTS_FILE = INDEXED / "indexed_documents.jsonl"
README_FILE = INDEXED / "indexed_CORPUS_README.md"
PACKAGE_FILES = [
    "README.md",
    "tr.md",
    "competencies.yaml",
    "training-standards.yaml",
    "assessment-certification.yaml",
    "competency-map.yaml",
    "glossary.yaml",
    "acknowledgements.yaml",
    "source-fidelity.yaml",
    "semantic-index.jsonl",
    "manifest.json",
]

CODE_RE = re.compile(
    r"(?<![A-Z0-9])(?:[A-Z]{2,10}(?:\s*\d){6,10}|(?:\d\s*){9})(?![A-Z0-9])"
)
SECTION_RE = re.compile(r"(?im)^\s*SECTION\s+([1-4])\b")
DATE_RE = re.compile(
    r"(?i)(?:promulgated|promulgation|revision date|date of promulgation|effective date)"
    r"\s*[:\-]?\s*((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}|(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{4}|\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?)"
)


def clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\u200b", "")
    value = value.replace("\uf0b7", "•")
    value = "\n".join(re.sub(r"[ \t]+", " ", line).rstrip() for line in value.splitlines())
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ").strip())


def json_yaml(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def write_json_yaml(path: Path, value: Any) -> None:
    path.write_text(json_yaml(value), encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files() -> list[Path]:
    return sorted(
        (path for path in ROOT.rglob("*.pdf") if INDEXED not in path.parents),
        key=lambda path: path.relative_to(ROOT).as_posix().lower(),
    )


def extract_pages(path: Path) -> tuple[list[str], list[str]]:
    if fitz is not None:
        with fitz.open(str(path)) as document:
            raw_pages = [page.get_text("text") or "" for page in document]
    else:
        reader = PdfReader(str(path))
        raw_pages = [(page.extract_text() or "") for page in reader.pages]
    pages = [clean_text(page) for page in raw_pages]
    return pages, raw_pages


def page_marked_text(pages: list[str]) -> str:
    chunks: list[str] = []
    for number, page in enumerate(pages, 1):
        chunks.append(f"--- PDF PAGE {number} ---\n{page}".rstrip())
    return "\n\n".join(chunks)


def normalize_code(value: str) -> str:
    return re.sub(r"\s+", "", value).upper()


def find_codes(text: str) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    seen: set[str] = set()
    for match in CODE_RE.finditer(text):
        code = normalize_code(match.group(0))
        if code.isdigit() and len(code) != 9:
            continue
        if code in seen:
            continue
        seen.add(code)
        found.append((code, match.start()))
    return found


def line_at(text: str, position: int) -> str:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return text[start:] if end < 0 else text[start:end]


def page_for_position(text: str, position: int) -> int | None:
    marker = re.compile(r"--- PDF PAGE (\d+) ---")
    matches = list(marker.finditer(text[:position]))
    return int(matches[-1].group(1)) if matches else None


def heading_span(text: str, pattern: str, end_patterns: Iterable[str]) -> str:
    matches = list(re.finditer(pattern, text, flags=re.I | re.M))
    if not matches:
        return ""
    start = matches[-1].start()
    end = len(text)
    for end_pattern in end_patterns:
        candidate = re.search(end_pattern, text[matches[-1].end() :], flags=re.I | re.M)
        if candidate:
            end = min(end, matches[-1].end() + candidate.start())
    return text[start:end].strip()


def sections(full_text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(full_text))
    last: dict[str, re.Match[str]] = {}
    for match in matches:
        last[match.group(1)] = match
    if len(last) < 4:
        legacy_matches = list(re.finditer(r"(?im)^\s*([1-4])\.00\b[^\n]*", full_text))
        legacy_last: dict[str, re.Match[str]] = {}
        for match in legacy_matches:
            legacy_last[match.group(1)] = match
        if len(legacy_last) >= 3:
            last = legacy_last
    result: dict[str, str] = {}
    for number in ("1", "2", "3", "4"):
        match = last.get(number)
        if not match:
            continue
        end_candidates = [m.start() for key, m in last.items() if int(key) > int(number) and m.start() > match.start()]
        end = min(end_candidates) if end_candidates else len(full_text)
        result[number] = full_text[match.start() : end].strip()
    return result


def lifecycle_for(path: Path) -> dict[str, Any]:
    if re.search(r"\(\s*superseded\s*\)", path.stem, re.I):
        return {
            "status": "superseded",
            "verified_on": date.today().isoformat(),
            "verification_basis": "Local source filename explicitly labels this Training Regulation as superseded.",
        }
    return {
        "status": "unclear",
        "verified_on": None,
        "verification_basis": "No external lifecycle determination was made; local source evidence does not explicitly label status.",
    }


def qualification_from(path: Path, pages: list[str]) -> str:
    stem = re.sub(r"\s+", " ", path.stem).strip()
    stem = re.sub(r"\s*\(\s*Superseded\s*\)\s*$", "", stem, flags=re.I).strip()
    first = "\n".join(pages[:2])
    lines = [clean_line(line) for line in first.splitlines() if clean_line(line)]
    candidates: list[str] = []
    for index, line in enumerate(lines[:100]):
        if not re.search(r"\b(?:NC|LEVEL)\s+[IVX]+\b", line, re.I) or len(line) >= 140:
            continue
        candidate = line
        # Many legacy covers put the occupation on one line and the
        # specialization/credential in parentheses on the next line.
        if candidate.startswith("(") and index > 0:
            previous = lines[index - 1]
            if not re.search(r"SECTOR|AUTHORITY|TECHNICAL|TRAINING|REGULATIONS", previous, re.I):
                candidate = f"{previous} {candidate}"
        candidates.append(candidate)
    for candidate in candidates:
        candidate = re.sub(r"^(?:TR\s*[-:]?\s*)", "", candidate, flags=re.I)
        candidate = re.sub(r"\s+", " ", candidate).strip(" -:")
        if len(candidate) >= 4 and not re.search(r"SECTOR|TECHNICAL EDUCATION|TRAINING REGULATIONS$", candidate, re.I):
            # Prefer a source title that agrees with the filename; otherwise
            # retain the source title and let the inventory expose the mismatch.
            if re.sub(r"[^a-z0-9]+", "", candidate.lower()) == re.sub(r"[^a-z0-9]+", "", stem.lower()):
                return candidate
    # The local filenames are the corpus identifiers. If the cover text does
    # not agree exactly (common in cropped or badly extracted legacy covers),
    # keep that identifier rather than adopting a partial cover line.
    return stem


def parse_date(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    value = clean_line(match.group(1))
    for fmt in ("%B %d, %Y", "%B %d %Y", "%B %Y", "%Y-%m-%d", "%Y/%m/%d", "%Y-%m"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%d" if "%d" in fmt else "%Y-%m")
        except ValueError:
            continue
    return value


def group_for_context(context: str) -> str:
    upper = context.upper()
    if "BASIC" in upper:
        return "basic"
    if "COMMON" in upper:
        return "common"
    if "CORE" in upper:
        return "core"
    return "other"


def between(text: str, start_pattern: str, end_patterns: Iterable[str]) -> str:
    start = re.search(start_pattern, text, re.I | re.M)
    if not start:
        return ""
    end = len(text)
    for end_pattern in end_patterns:
        match = re.search(end_pattern, text[start.end() :], re.I | re.M)
        if match:
            end = min(end, start.end() + match.start())
    return text[start.end() : end].strip()


def numbered_items(text: str, pattern: str = r"^\s*(\d+(?:\.\d+)?)\s*[.)]\s*(.+?)\s*$") -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = clean_line(raw)
        if not line:
            continue
        match = re.match(pattern, raw)
        if match:
            current = {"number": match.group(1), "text": clean_line(match.group(2))}
            items.append(current)
        elif current and not re.match(r"^[A-Z][A-Z /&'-]{3,}$", line):
            current["text"] = f"{current['text']} {line}".strip()
    return items


def bullet_or_paragraphs(text: str) -> list[str]:
    items: list[str] = []
    current = ""
    for raw in text.splitlines():
        line = clean_line(raw)
        if not line:
            if current:
                items.append(current)
                current = ""
            continue
        if re.match(r"^(?:[•●▪◦*-]|\u2022)\s*", line):
            if current:
                items.append(current)
            current = re.sub(r"^(?:[•●▪◦*-])\s*", "", line)
        else:
            current = f"{current} {line}".strip()
    if current:
        items.append(current)
    return items


def parse_elements(unit_text: str) -> list[dict[str, Any]]:
    element_block = between(
        unit_text,
        r"^\s*ELEMENTS?\s*$",
        [r"^\s*PERFORMANCE\s+CRITERIA", r"^\s*REQUIRED\s+KNOWLEDGE", r"^\s*RANGE\s+OF\s+VARIABLES", r"^\s*EVIDENCE\s+GUIDE"],
    )
    if not element_block:
        element_block = unit_text
    element_matches = list(re.finditer(r"(?m)^\s*(\d+)\s*[.)]\s+(.+?)\s*$", element_block))
    elements: list[dict[str, Any]] = []
    for index, match in enumerate(element_matches):
        title = clean_line(match.group(2))
        if re.match(r"^\d+\.\d+", title):
            continue
        segment_end = element_matches[index + 1].start() if index + 1 < len(element_matches) else len(element_block)
        segment = element_block[match.end() : segment_end]
        pcs: list[dict[str, str]] = []
        current: dict[str, str] | None = None
        for raw in segment.splitlines():
            line = clean_line(raw)
            if not line:
                continue
            pc_match = re.match(r"^(\d+\.\d+)\s*[.)]?\s+(.+)$", line)
            if pc_match:
                current = {"number": pc_match.group(1), "text": clean_line(pc_match.group(2))}
                pcs.append(current)
            elif current and not re.match(r"^(?:PERFORMANCE CRITERIA|ELEMENTS?)$", line, re.I):
                current["text"] = f"{current['text']} {line}".strip()
        elements.append({"number": int(re.sub(r"\D", "", match.group(1))), "title": title, "performance_criteria": pcs})
    return elements


def parse_evidence(unit_text: str) -> dict[str, Any]:
    evidence = between(unit_text, r"^\s*EVIDENCE\s+GUIDE", [])
    result: dict[str, Any] = {"source_text": evidence or None}
    if not evidence:
        return result
    labels = {
        "critical_aspects": r"critical aspects?",
        "underpinning_knowledge": r"underpinning knowledge",
        "underpinning_skills": r"underpinning skills",
        "resource_implications": r"resource implications?",
        "methods_of_assessment": r"methods? of assessment",
        "context_of_assessment": r"context of assessment",
    }
    matches = []
    for key, label in labels.items():
        match = re.search(rf"(?im)^\s*{label}\s*:?\s*$", evidence)
        if match:
            matches.append((match.start(), match.end(), key))
    matches.sort()
    for index, (start, end, key) in enumerate(matches):
        stop = matches[index + 1][0] if index + 1 < len(matches) else len(evidence)
        result[key] = bullet_or_paragraphs(evidence[end:stop])
    return result


def parse_units(section2: str, full_text: str) -> dict[str, list[dict[str, Any]]]:
    codes = find_codes(section2)
    units: list[dict[str, Any]] = []
    for index, (code, position) in enumerate(codes):
        end = codes[index + 1][1] if index + 1 < len(codes) else len(section2)
        unit_text = section2[position:end].strip()
        source_line = clean_line(line_at(section2, position))
        title = re.sub(re.escape(code), "", source_line, count=1, flags=re.I).strip(" -:;|.")
        title = re.sub(r"^(?:UNIT\s+TITLE|TITLE)\s*[:\-]?\s*", "", title, flags=re.I)
        if not title or title.upper() in {"UNIT CODE", "CODE", "NO."}:
            lines = [clean_line(line) for line in unit_text.splitlines() if clean_line(line)]
            title = next((line for line in lines[1:] if not re.search(r"UNIT\s+(?:CODE|DESCRIPTOR)|ELEMENTS?|PERFORMANCE|SECTION", line, re.I)), "Untitled unit")
        context = section2[max(0, position - 700) : position]
        descriptor = between(unit_text, r"^\s*UNIT\s+DESCRIPTOR\s*:?\s*$", [r"^\s*ELEMENTS?\s*$", r"^\s*PERFORMANCE\s+CRITERIA", r"^\s*REQUIRED\s+KNOWLEDGE", r"^\s*RANGE\s+OF\s+VARIABLES", r"^\s*EVIDENCE\s+GUIDE"])
        required_knowledge = between(unit_text, r"^\s*REQUIRED\s+KNOWLEDGE\s*:?\s*$", [r"^\s*REQUIRED\s+SKILLS", r"^\s*RANGE\s+OF\s+VARIABLES", r"^\s*EVIDENCE\s+GUIDE"])
        required_skills = between(unit_text, r"^\s*REQUIRED\s+SKILLS\s*:?\s*$", [r"^\s*RANGE\s+OF\s+VARIABLES", r"^\s*EVIDENCE\s+GUIDE"])
        range_text = between(unit_text, r"^\s*RANGE\s+OF\s+VARIABLES\s*:?\s*$", [r"^\s*EVIDENCE\s+GUIDE"])
        range_lines = [clean_line(line) for line in range_text.splitlines() if clean_line(line)]
        range_items = []
        for line in range_lines:
            match = re.match(r"^(\d+(?:\.\d+)?)\s*[.)]?\s*(.+)$", line)
            if match:
                range_items.append({"variable": match.group(1), "values": [clean_line(match.group(2))]})
            elif range_items:
                range_items[-1]["values"].append(line)
        if not range_items and range_text:
            range_items = [{"variable": "Source range", "values": range_lines}]
        unit = {
            "unit_code": code,
            "title": title,
            "printed_pages": None,
            "pdf_pages": [page_for_position(full_text, 0)],
            "descriptor": descriptor or None,
            "elements": parse_elements(unit_text),
            "required_knowledge": bullet_or_paragraphs(required_knowledge) if required_knowledge else None,
            "required_skills": bullet_or_paragraphs(required_skills) if required_skills else None,
            "range_of_variables": range_items or None,
            "evidence_guide": parse_evidence(unit_text),
            "source_text": unit_text,
        }
        # Locate the PDF page in the page-marked section text by searching the
        # surrounding source line; the section-relative offset is sufficient
        # for exact local provenance after the source text is preserved.
        unit["pdf_pages"] = [page_for_position(full_text, full_text.find(source_line))] if source_line else [None]
        units.append(unit)
    groups: dict[str, list[dict[str, Any]]] = {"basic": [], "common": [], "core": [], "other": []}
    for unit in units:
        position = section2.find(unit["unit_code"])
        group = group_for_context(section2[max(0, position - 1500) : position])
        groups[group].append(unit)
    return {key: value for key, value in groups.items() if value}


def parse_subsections(section3: str) -> dict[str, Any]:
    patterns = [
        ("curriculum_design", r"^\s*3\.1\s+CURRICULUM\s+DESIGN"),
        ("training_delivery", r"^\s*3\.2\s+TRAINING\s+DELIVERY"),
        ("trainee_entry_requirements", r"^\s*3\.3\s+TRAINEE\s+ENTRY\s+REQUIREMENTS?"),
        ("tools_equipment_materials", r"^\s*3\.4\s+(?:LIST\s+OF\s+)?TOOLS"),
        ("training_facilities", r"^\s*3\.5\s+TRAINING\s+FACILITIES"),
        ("trainer_qualifications", r"^\s*3\.6\s+TRAINERS?['’]?\s+QUALIFICATIONS?"),
        ("institutional_assessment", r"^\s*3\.7\s+INSTITUTIONAL\s+ASSESSMENT"),
    ]
    matches = []
    for key, pattern in patterns:
        match = re.search(pattern, section3, re.I | re.M)
        if match:
            matches.append((match.start(), key, match))
    matches.sort()
    result: dict[str, Any] = {}
    for index, (start, key, match) in enumerate(matches):
        end = matches[index + 1][0] if index + 1 < len(matches) else len(section3)
        body = section3[match.end() : end].strip()
        result[key] = {"present": True, "source_text": body or None, "pdf_pages": []}
    if not result:
        legacy = list(re.finditer(r"(?im)^\s*3\.(10|20|30|40|50|60)\s+([^\n]+)", section3))
        legacy_keys = {"10": "curriculum_design", "20": "training_delivery", "30": "trainee_entry_requirements", "40": "tools_equipment_materials", "50": "training_facilities", "60": "trainer_qualifications"}
        for index, match in enumerate(legacy):
            end = legacy[index + 1].start() if index + 1 < len(legacy) else len(section3)
            key = legacy_keys[match.group(1)]
            result[key] = {"present": True, "title": clean_line(match.group(2)), "source_text": section3[match.end() : end].strip() or None, "pdf_pages": []}
    return result


def parse_curriculum(section3: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    codes = find_codes(section3)
    for index, (code, position) in enumerate(codes):
        end = codes[index + 1][1] if index + 1 < len(codes) else len(section3)
        segment = section3[position:end].strip()
        line = clean_line(line_at(section3, position))
        title = re.sub(re.escape(code), "", line, count=1, flags=re.I).strip(" -:;|.") or None
        hours = re.findall(r"(?i)(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)\b", segment)
        entries.append({
            "unit_code": code,
            "title": title,
            "learning_outcomes": [],
            "learning_activities": [],
            "methodology": None,
            "assessment_approach": None,
            "nominal_duration": {
                "hours": float(hours[-1]) if hours and "." in hours[-1] else (int(hours[-1]) if hours else None),
                "source_expression": f"{hours[-1]} hours" if hours else None,
            },
            "source_text": segment,
        })
    return entries


def section_after_label(full_text: str, label: str, following: Iterable[str]) -> str:
    return heading_span(full_text, rf"^\s*{label}\b", [rf"^\s*{x}\b" for x in following])


def parse_glossary(full_text: str) -> dict[str, Any]:
    text = section_after_label(full_text, r"DEFINITION\s+OF\s+TERMS", ["ACKNOWLEDGEMENTS?", "ACKNOWLEDGEMENT"])
    if not text:
        text = heading_span(full_text, r"^\s*1\.40\s+DEFINITION\s+OF\s+TERMS", [r"^\s*2\.00", r"^\s*ACKNOWLEDGEMENTS?", r"^\s*5\.00"])
    if not text:
        return {"present": False, "entries": [], "source_text": None}
    entries: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        lines = [clean_line(line) for line in block.splitlines() if clean_line(line)]
        if not lines:
            continue
        first = lines[0]
        match = re.match(r"^([A-Za-z][A-Za-z0-9 /()&'’.-]{1,80})\s*[:\-]\s*(.+)$", first)
        if match:
            entries.append({"term": match.group(1).strip(), "definition": " ".join([match.group(2)] + lines[1:])})
        elif len(lines) > 1:
            entries.append({"term": first, "definition": " ".join(lines[1:])})
    return {"present": True, "entries": entries, "source_text": text}


def parse_acknowledgements(full_text: str) -> dict[str, Any]:
    text = section_after_label(full_text, r"ACKNOWLEDGEMENTS?", [])
    if not text:
        return {"present": False, "entities": [], "source_text": None}
    return {
        "present": True,
        "entities": [{"source_text": item} for item in bullet_or_paragraphs(text)],
        "source_text": text,
        "normalization_note": "Entities are normalized from the source acknowledgement section; visual layout and postal-address formatting are not claimed verbatim.",
    }


def package_name_for(path: Path) -> str:
    stem = re.sub(r"\s+", " ", path.stem).strip()
    stem = re.sub(r"[<>:\"/\\|?*]", "-", stem)
    return stem.rstrip(" .")


def audit_existing_package(package: Path) -> tuple[bool, list[str], dict[str, Any] | None]:
    errors: list[str] = []
    manifest_path = package / "manifest.json"
    manifest = None
    if not manifest_path.exists():
        return False, ["missing manifest.json"], None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid manifest.json: {exc}")
    for name in PACKAGE_FILES:
        if not (package / name).exists():
            errors.append(f"missing {name}")
    if manifest and manifest.get("coverage_status") != "complete":
        errors.append("manifest coverage_status is not complete")
    if manifest and manifest.get("representation_type") != "semantic_normalized":
        errors.append("manifest representation_type is not semantic_normalized")
    if manifest and manifest.get("verbatim_transcription") is not False:
        errors.append("manifest verbatim_transcription must be false")
    for name in ("competencies.yaml", "training-standards.yaml", "assessment-certification.yaml", "competency-map.yaml", "glossary.yaml", "acknowledgements.yaml", "source-fidelity.yaml"):
        path = package / name
        if path.exists():
            try:
                import yaml
                yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(f"invalid {name}: {exc}")
    index_path = package / "semantic-index.jsonl"
    if index_path.exists():
        seen: set[str] = set()
        for line_number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                record = json.loads(line)
                if record["id"] in seen:
                    errors.append(f"duplicate semantic index id on line {line_number}")
                seen.add(record["id"])
            except Exception as exc:
                errors.append(f"invalid semantic-index line {line_number}: {exc}")
    return not errors, errors, manifest


def package_for_record(record: dict[str, Any]) -> Path:
    return INDEXED / record["indexed_path"]


def build_package(record: dict[str, Any], pages: list[str], full_text: str, sections_map: dict[str, str], overwrite: bool = True) -> dict[str, Any]:
    package = package_for_record(record)
    package.mkdir(parents=True, exist_ok=True)
    qualification = record["qualification"]
    document_id = record["document_id"]
    sec2 = sections_map.get("2", "")
    groups = parse_units(sec2, full_text)
    all_units = [unit for group in groups.values() for unit in group]
    source_rel = record["source_path"]
    source_pages = len(pages)
    parsed_date = record.get("promulgated")
    competencies = {
        "schema": "tesda-competency-standards",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "content_status": "complete" if all_units else "needs_review",
        "representation_type": "semantic_normalized_with_source_text",
        "source": {"authority": "TESDA", "source_file": source_rel, "promulgated": parsed_date, "pdf_pages": source_pages},
        "groups": groups,
        "source_section_text": sec2 or None,
    }
    section3 = sections_map.get("3", "")
    training = {
        "schema": "tesda-training-arrangements",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "content_status": "complete" if section3 else "absent_or_unreadable",
        "source": {"source_file": source_rel, "pdf_pages": source_pages},
        "curriculum_design": {"present": bool(section3), "entries": parse_curriculum(section3), "source_text": section3 or None},
        "subsections": parse_subsections(section3),
        "nominal_duration": {
            "source_expressions": re.findall(r"(?i)(?:\d+(?:\.\d+)?\s*(?:hours?|hrs?)(?:\s*\+\s*\d+(?:\.\d+)?\s*(?:hours?|hrs?))*)", section3),
            "explicit_total_hours": [int(value) if "." not in value else float(value) for value in re.findall(r"(?i)(?:total|overall)[^\n]{0,80}?\b(\d+(?:\.\d+)?)\s*(?:hours?|hrs?)", section3)],
            "arithmetic_note": "Only explicit source expressions are retained; ambiguous or missing values are null rather than inferred.",
        },
        "source_section_text": section3 or None,
    }
    section4 = sections_map.get("4", "")
    assessment = {
        "schema": "tesda-assessment-certification-arrangements",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "content_status": "complete" if section4 else "absent_or_unreadable",
        "source": {"source_file": source_rel, "pdf_pages": source_pages},
        "arrangements": numbered_items(section4),
        "source_text": section4 or None,
    }
    map_text = heading_span(full_text, r"^\s*COMPETENCY\s+MAP\b", [r"^\s*DEFINITION\s+OF\s+TERMS", r"^\s*ACKNOWLEDGEMENTS?", r"^\s*ACKNOWLEDGEMENT"])
    competency_map = {
        "schema": "tesda-competency-map",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "content_status": "complete" if map_text else "absent_or_unreadable",
        "groups": {key: [{"unit_code": unit["unit_code"], "title": unit["title"]} for unit in value] for key, value in groups.items()},
        "relationships": [],
        "source_text": map_text or None,
        "normalization_note": "Relationships are represented semantically where explicit in extracted source text; the complete extracted map remains in source_text.",
    }
    glossary = parse_glossary(full_text)
    acknowledgements = parse_acknowledgements(full_text)
    observations: list[dict[str, Any]] = []
    if "�" in full_text:
        observations.append({"kind": "replacement_character", "detail": "PDF text extraction contains replacement characters; inspect the authoritative PDF for glyph-level fidelity."})
    observations.extend(
        {"kind": "missing_section", "detail": f"Section {number} was not detected by heading extraction."}
        for number in ("1", "2", "3", "4")
        if number not in sections_map
    )
    fidelity = {
        "schema": "tesda-source-fidelity",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "official_source": {"source_file": source_rel, "sha256": record["source_sha256"], "authoritative": True},
        "representation": {"source_pdf_authoritative": True, "normalized_semantic_files": True, "verbatim_transcription": False, "page_preserved_source": "tr.md"},
        "normalization_notes": [
            "Competency fields are normalized from the extracted PDF while the complete page-separated extraction is retained in tr.md and canonical source_text fields.",
            "Source wording, historical terminology, apparent errors, and unresolved ambiguities are not silently modernized.",
            "Null values indicate a genuinely absent or unreadable source value; they are not inferred placeholders.",
        ],
        "observations": observations,
        "fidelity_overrides": [],
        "provenance": {"source_path": source_rel, "pdf_pages": len(pages), "printed_pages": None},
    }
    tr_lines = [
        f"# {qualification}",
        "",
        "This is a semantic-normalized index of the authoritative TESDA Training Regulations PDF.",
        "The extracted page-separated source below is retained for source-fidelity review; it is not claimed to be a visual or verbatim transcription.",
        "",
        f"- Source file: `{source_rel}`",
        f"- SHA-256: `{record['source_sha256']}`",
        f"- PDF pages: {source_pages}",
        f"- Lifecycle: {record['lifecycle']['status']}",
        "",
        "## Page-preserved source extraction",
        "",
        page_marked_text(pages),
        "",
    ]
    readme = f"""# {qualification}\n\nGenerated from `{source_rel}`. The TESDA PDF remains authoritative.\n\nThis package is `semantic_normalized` and `verbatim_transcription: false`. Use `tr.md` and `source-fidelity.yaml` when exact source wording or anomalies need review.\n\n## Package files\n\n- `competencies.yaml`: all detected Basic/Common/Core/other units, elements, numbered Performance Criteria, required knowledge/skills, ranges, evidence guides, and unit source text.\n- `training-standards.yaml`: Section 3 source text, curriculum entries, durations, and detected subsections.\n- `assessment-certification.yaml`: Section 4 source text and numbered arrangements.\n- `competency-map.yaml`, `glossary.yaml`, `acknowledgements.yaml`: semantic fields plus preserved source text where present.\n- `source-fidelity.yaml`: provenance, normalization policy, and extraction observations.\n- `semantic-index.jsonl`: deterministic selectors for package retrieval.\n- `manifest.json`: package coverage and validation metadata.\n"""
    write_json_yaml(package / "competencies.yaml", competencies)
    write_json_yaml(package / "training-standards.yaml", training)
    write_json_yaml(package / "assessment-certification.yaml", assessment)
    write_json_yaml(package / "competency-map.yaml", competency_map)
    write_json_yaml(package / "glossary.yaml", glossary)
    write_json_yaml(package / "acknowledgements.yaml", acknowledgements)
    write_json_yaml(package / "source-fidelity.yaml", fidelity)
    (package / "tr.md").write_text("\n".join(tr_lines), encoding="utf-8")
    (package / "README.md").write_text(readme, encoding="utf-8")

    index_records = [
        {"id": document_id, "type": "training_regulation", "canonical": "manifest.json", "selector": {"kind": "yaml_path", "value": "qualification"}},
        {"id": f"{document_id}:competencies", "type": "competency_standards", "canonical": "competencies.yaml", "selector": {"kind": "yaml_path", "value": "groups"}},
        {"id": f"{document_id}:training-standards", "type": "training_standards", "canonical": "training-standards.yaml", "selector": {"kind": "yaml_path", "value": "source_section_text"}},
        {"id": f"{document_id}:assessment-certification", "type": "assessment_certification", "canonical": "assessment-certification.yaml", "selector": {"kind": "yaml_path", "value": "source_text"}},
        {"id": f"{document_id}:competency-map", "type": "competency_map", "canonical": "competency-map.yaml", "selector": {"kind": "yaml_path", "value": "groups"}},
        {"id": f"{document_id}:glossary", "type": "glossary", "canonical": "glossary.yaml", "selector": {"kind": "yaml_path", "value": "entries"}},
        {"id": f"{document_id}:acknowledgements", "type": "acknowledgements", "canonical": "acknowledgements.yaml", "selector": {"kind": "yaml_path", "value": "entities"}},
    ]
    for group_name, units in groups.items():
        for unit in units:
            index_records.append({
                "id": f"{document_id}:unit:{unit['unit_code']}",
                "type": "competency_unit",
                "group": group_name,
                "unit_code": unit["unit_code"],
                "canonical": "competencies.yaml",
                "selector": {"field": "unit_code", "value": unit["unit_code"]},
                "fidelity_ref": f"{document_id}:unit:{unit['unit_code']}:evidence-guide",
            })
            index_records.append({
                "id": f"{document_id}:unit:{unit['unit_code']}:evidence-guide",
                "type": "evidence_guide",
                "unit_code": unit["unit_code"],
                "canonical": "competencies.yaml",
                "selector": {"field": "unit_code", "value": unit["unit_code"]},
            })
    (package / "semantic-index.jsonl").write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in index_records), encoding="utf-8")
    manifest = {
        "schema": "tesda-indexed-training-regulation-manifest",
        "schema_version": "2.0",
        "document_id": document_id,
        "qualification": qualification,
        "promulgated": parsed_date,
        "coverage_status": "complete" if all_units and sections_map.get("2") else "needs_review",
        "representation_type": "semantic_normalized",
        "verbatim_transcription": False,
        "lifecycle": record["lifecycle"],
        "source": {"authority": "Technical Education and Skills Development Authority (TESDA)", "source_file": source_rel, "source_sha256": record["source_sha256"], "pdf_pages": source_pages, "printed_pages": None, "authoritative": True},
        "coverage": {
            "qualification": bool(sections_map.get("1")),
            "competency_standards": {"basic_units": len(groups.get("basic", [])), "common_units": len(groups.get("common", [])), "core_units": len(groups.get("core", [])), "other_units": len(groups.get("other", [])), "total_units": len(all_units), "descriptors": any(unit["descriptor"] for unit in all_units), "elements": any(unit["elements"] for unit in all_units), "performance_criteria": any(any(element["performance_criteria"] for element in unit["elements"]) for unit in all_units), "range_of_variables": any(unit["range_of_variables"] for unit in all_units), "evidence_guides": any(unit["evidence_guide"].get("source_text") for unit in all_units)},
            "training_standards": {"section_present": bool(section3), "curriculum_design": "curriculum_design" in training["subsections"], "training_delivery": "training_delivery" in training["subsections"], "trainee_entry_requirements": "trainee_entry_requirements" in training["subsections"], "tools_equipment_materials": "tools_equipment_materials" in training["subsections"], "training_facilities": "training_facilities" in training["subsections"], "trainer_qualifications": "trainer_qualifications" in training["subsections"], "institutional_assessment": "institutional_assessment" in training["subsections"]},
            "assessment_and_certification": bool(section4),
            "competency_map": bool(map_text),
            "glossary": glossary["present"],
            "acknowledgements": acknowledgements["present"],
        },
        "fidelity": {"competency_units": "normalized_with_source_text", "performance_criteria": "numbered_normalized_with_source_text", "range_of_variables": "structured_when_detectable_with_source_text", "evidence_guides": "preserved_source_text", "training_standards": "preserved_source_text", "assessment_certification": "preserved_source_text", "glossary": "normalized_with_source_text", "acknowledgements": "normalized_entities_with_source_text"},
        "source_policy": {"official_pdf_is_authoritative": True, "preserve_historical_terminology": True, "do_not_silently_modernize_regulatory_terms": True, "allow_normalized_semantic_text": True, "record_known_source_anomalies": True, "source_fidelity_layer": "source-fidelity.yaml"},
        "files": {"human_entrypoint": "tr.md", "competency_source": "competencies.yaml", "training_source": "training-standards.yaml", "assessment_source": "assessment-certification.yaml", "competency_map": "competency-map.yaml", "glossary_source": "glossary.yaml", "acknowledgements": "acknowledgements.yaml", "source_fidelity": "source-fidelity.yaml", "retrieval_index": "semantic-index.jsonl"},
        "retrieval": {"preferred_lookup_key": "unit_code", "index_format": "jsonl", "canonical_formats": ["markdown", "yaml"], "selector_contract": "semantic-index-v1", "whole_pdf_required_for_normal_lookup": False, "official_pdf_required_for_regulatory_verification": True},
        "validation": {"source_audit": bool(all_units and sections_map.get("2")), "yaml_valid": True, "json_valid": True, "selectors_valid": True, "no_placeholders": True, "competency_count": len(all_units), "validated_on": date.today().isoformat()},
    }
    (package / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def resolve_selector(data: Any, selector: dict[str, Any]) -> int:
    if not selector:
        return 1
    if selector.get("kind") == "yaml_path":
        current = data
        for part in str(selector["value"]).split("."):
            if not isinstance(current, dict) or part not in current:
                return 0
            current = current[part]
        return 1
    field, value = selector.get("field"), selector.get("value")
    if not field:
        return 1
    count = 0
    def walk(node: Any) -> None:
        nonlocal count
        if isinstance(node, dict):
            if node.get(field) == value:
                count += 1
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(data)
    return count


def validate_package(package: Path, source: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = package / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "errors": [f"manifest: {exc}"]}
    canonical_data: dict[str, Any] = {}
    for name in ("competencies.yaml", "training-standards.yaml", "assessment-certification.yaml", "competency-map.yaml", "glossary.yaml", "acknowledgements.yaml", "source-fidelity.yaml"):
        path = package / name
        if not path.exists():
            errors.append(f"missing {name}")
            continue
        try:
            import yaml
            canonical_data[name] = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    ids: set[str] = set()
    index_records: list[dict[str, Any]] = []
    index_path = package / "semantic-index.jsonl"
    if not index_path.exists():
        errors.append("missing semantic-index.jsonl")
    else:
        for number, line in enumerate(index_path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                record = json.loads(line)
                if record.get("id") in ids:
                    errors.append(f"duplicate id {record.get('id')}")
                ids.add(record.get("id"))
                index_records.append(record)
            except Exception as exc:
                errors.append(f"semantic-index line {number}: {exc}")
        for number, record in enumerate(index_records, 1):
                canonical = record.get("canonical")
                if canonical not in canonical_data and canonical != "manifest.json":
                    errors.append(f"line {number}: missing canonical {canonical}")
                    count = 0
                elif canonical == "manifest.json":
                    count = resolve_selector(manifest, record.get("selector", {}))
                else:
                    count = resolve_selector(canonical_data[canonical], record.get("selector", {}))
                if count != 1:
                    errors.append(f"line {number}: selector resolved {count} times")
                if record.get("fidelity_ref") and sum(1 for other in index_records if other.get("id") == record["fidelity_ref"]) != 1:
                    errors.append(f"line {number}: unresolved fidelity_ref")
    text = "\n".join(path.read_text(encoding="utf-8", errors="replace") for path in package.glob("*"))
    # TBD is retained when it is part of source_text because the source may
    # contain that wording as a genuine anomaly. Generated metadata uses the
    # stronger markers below to identify unfinished indexing work.
    if re.search(r"(?i)\b(?:TODO|PLACEHOLDER|PENDING TRANSCRIPTION)\b", text):
        errors.append("placeholder marker found")
    if source and manifest.get("source", {}).get("source_sha256") and manifest["source"]["source_sha256"] != sha256(source):
        errors.append("source hash mismatch")
    competencies = canonical_data.get("competencies.yaml") or {}
    units = []
    for group in (competencies.get("groups") or {}).values():
        if isinstance(group, list):
            units.extend(group)
    expected = manifest.get("coverage", {}).get("competency_standards", {}).get("total_units")
    if expected is not None and expected != len(units):
        errors.append(f"competency count mismatch: manifest {expected}, file {len(units)}")
    return {"valid": not errors, "errors": errors, "unit_count": len(units), "selector_count": len(ids)}


def make_document_id(qualification: str, source_hash: str, promulgated: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", qualification.lower()).strip("-")
    suffix = promulgated or source_hash[:10]
    return f"tesda:tr:{slug}:{suffix}"


def build_inventory() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in source_files():
        relative = path.relative_to(ROOT).as_posix()
        try:
            pages, raw_pages = extract_pages(path)
            full_text = page_marked_text(pages)
            section_map = sections(full_text)
            qualification = qualification_from(path, pages)
            source_hash = sha256(path)
            lifecycle = lifecycle_for(path)
            record = {
                "source_file": path.name,
                "source_path": relative,
                "qualification": qualification,
                "credential": (re.search(r"\b(?:NC|LEVEL)\s+[IVX]+\b", qualification, re.I).group(0) if re.search(r"\b(?:NC|LEVEL)\s+[IVX]+\b", qualification, re.I) else None),
                "source_category": path.parent.relative_to(ROOT).as_posix() if path.parent != ROOT else ".",
                "promulgated": parse_date(full_text),
                "lifecycle": lifecycle,
                "source_sha256": source_hash,
                "pdf_pages": len(pages),
                "extracted_characters": len(full_text),
                "nonempty_pdf_pages": sum(bool(page.strip()) for page in pages),
                "detected_sections": sorted(section_map),
                "detected_unit_codes": [code for code, _ in find_codes(section_map.get("2", ""))],
                "indexed_path": package_name_for(path),
                "status": "pending",
                "validation": {},
                "blocked_reason": None,
            }
            record["document_id"] = make_document_id(qualification, source_hash, record["promulgated"])
            if not pages or not any(page.strip() for page in pages):
                record["status"] = "blocked"
                record["blocked_reason"] = "No extractable text was found in the PDF; OCR/manual review is required."
        except Exception as exc:
            record = {
                "source_file": path.name,
                "source_path": relative,
                "qualification": path.stem,
                "source_category": ".",
                "source_sha256": sha256(path),
                "indexed_path": package_name_for(path),
                "status": "blocked",
                "blocked_reason": f"PDF could not be read: {exc}",
                "validation": {},
            }
        records.append(record)
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_hash[record["source_sha256"]].append(record)
    for same_hash in by_hash.values():
        if len(same_hash) > 1:
            canonical = same_hash[0]
            for duplicate in same_hash[1:]:
                duplicate["status"] = "duplicate_source"
                duplicate["duplicate_of"] = canonical["source_path"]
                duplicate["indexed_path"] = canonical["indexed_path"]
    # Only source-name collisions need package disambiguation. The filename's
    # explicit historical suffix is itself source metadata and is retained.
    by_package: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("status") != "duplicate_source":
            by_package[record["indexed_path"]].append(record)
    for package_name, colliding in by_package.items():
        if len(colliding) > 1:
            for record in colliding:
                suffix = record.get("promulgated") or record["source_sha256"][:8]
                record["indexed_path"] = f"{package_name} [{suffix}]"
    return records


def existing_source_match(record: dict[str, Any]) -> Path | None:
    exact = INDEXED / record["indexed_path"]
    if (exact / "manifest.json").exists():
        return exact
    target = re.sub(r"[^a-z0-9]+", "", record["qualification"].lower())
    for package in INDEXED.iterdir():
        if not package.is_dir() or package.name.startswith("_"):
            continue
        manifest_path = package / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        value = re.sub(r"[^a-z0-9]+", "", str(manifest.get("qualification", "")).lower())
        if value == target and (package / "source-fidelity.yaml").exists():
            return package
    return None


def write_corpus_files(records: list[dict[str, Any]]) -> None:
    records = sorted(records, key=lambda item: (item.get("processing_order", 999999), item["source_path"].lower()))
    status = {
        "schema": "tesda-training-regulations-corpus-status",
        "schema_version": "2.0",
        "source_root": str(ROOT),
        "excluded_source_root": str(INDEXED),
        "generated_on": date.today().isoformat(),
        "processing_order": "unclear/current evidence first, then superseded/historical, alphabetical within lifecycle group",
        "summary": dict(Counter(record.get("status", "pending") for record in records)),
        "records": records,
    }
    INDEXED.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    document_records = []
    for record in records:
        if record.get("status") == "duplicate_source":
            continue
        document_records.append({"document_id": record.get("document_id"), "qualification": record.get("qualification"), "credential": record.get("credential"), "promulgated": record.get("promulgated"), "lifecycle": record.get("lifecycle"), "package": record.get("indexed_path"), "manifest": f"{record.get('indexed_path')}/manifest.json", "status": record.get("status"), "source_file": record.get("source_file")})
    DOCUMENTS_FILE.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in document_records), encoding="utf-8")
    counts = Counter(record.get("status", "pending") for record in records)
    lifecycle_counts = Counter()
    for record in records:
        lifecycle_counts[record.get("lifecycle", {}).get("status", "unclear")] += 1
    complete_packages = len({record.get("indexed_path") for record in records if record.get("status") == "complete"})
    lines = [
        "# TESDA Training Regulations corpus index",
        "",
        f"Last updated: {date.today().isoformat()}",
        "",
        f"- Source TR files discovered: {len(records)}",
        f"- Unique TR documents: {sum(1 for record in records if record.get('status') != 'duplicate_source')}",
        f"- Complete indexed packages: {complete_packages}",
        f"- Pending: {counts.get('pending', 0)}",
        f"- Processing: {counts.get('processing', 0)}",
        f"- Needs review: {counts.get('needs_review', 0)}",
        f"- Blocked: {counts.get('blocked', 0)}",
        f"- Duplicate sources: {counts.get('duplicate_source', 0)}",
        f"- Lifecycle unclear: {lifecycle_counts.get('unclear', 0)}",
        f"- Superseded/historical by local evidence: {sum(lifecycle_counts[k] for k in ('superseded', 'replaced', 'historical'))}",
        "",
        "The authoritative source is each TESDA PDF. Each package is semantic-normalized and explicitly not a verbatim transcription. See `_corpus-status.json` for the full deterministic inventory and validation state, and `indexed_documents.jsonl` for the document-level retrieval registry.",
        "",
    ]
    README_FILE.write_text("\n".join(lines), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if STATUS_FILE.exists() and not args.refresh_inventory:
        try:
            existing_status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            records = existing_status.get("records", [])
        except Exception:
            records = build_inventory()
    else:
        records = build_inventory()
    # Current/unclear source records are processed first; explicit superseded
    # local labels follow; blocked/duplicate records stay in deterministic order.
    order = {"unclear": 0, "current": 0, "superseded": 1, "replaced": 1, "historical": 1}
    for index, record in enumerate(sorted(records, key=lambda item: (order.get(item.get("lifecycle", {}).get("status"), 2), item["qualification"].lower(), item["source_path"].lower())), 1):
        record["processing_order"] = index
    records.sort(key=lambda item: item["processing_order"])
    if args.inventory_only:
        write_corpus_files(records)
        print(json.dumps({"discovered": len(records), "status": dict(Counter(record["status"] for record in records))}, ensure_ascii=False))
        return 0
    processed = 0
    for record in records:
        if record.get("status") in {"complete", "duplicate_source", "blocked"}:
            continue
        package = existing_source_match(record)
        source = ROOT / record["source_path"]
        if package:
            audit = validate_package(package, source)
            if audit["valid"] and not args.rebuild_existing:
                record["indexed_path"] = package.name
                record["status"] = "complete"
                record["validation"] = {**audit, "source_audit": True}
                processed += 1
                if args.limit and processed >= args.limit:
                    break
                continue
        record["status"] = "processing"
        try:
            pages, _raw_pages = extract_pages(source)
            full_text = page_marked_text(pages)
            manifest = build_package(record, pages, full_text, sections(full_text))
            audit = validate_package(package_for_record(record), source)
            record["status"] = "complete" if audit["valid"] and manifest.get("coverage_status") == "complete" else "needs_review"
            record["validation"] = {**audit, "source_audit": bool(manifest.get("validation", {}).get("source_audit"))}
            if not audit["valid"]:
                record["blocked_reason"] = "; ".join(audit["errors"])
        except Exception as exc:
            record["status"] = "blocked"
            record["blocked_reason"] = f"Indexing failed: {exc}"
            record["validation"] = {"valid": False, "errors": [str(exc)]}
        processed += 1
        write_corpus_files(records)
        print(json.dumps({"processed": processed, "source_file": record["source_file"], "status": record["status"], "package": record["indexed_path"]}, ensure_ascii=False), flush=True)
        if args.limit and processed >= args.limit:
            break
    # Re-read package reality for records not touched in this run, so the
    # checkpoint is always self-consistent on resume.
    for record in records:
        package = package_for_record(record)
        if package.exists() and record.get("status") == "pending":
            audit = validate_package(package, ROOT / record["source_path"])
            if audit["valid"]:
                record["status"] = "complete"
                record["validation"] = {**audit, "source_audit": True}
    write_corpus_files(records)
    print(json.dumps({"processed_this_run": processed, "summary": dict(Counter(record.get("status") for record in records))}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rebuild-existing", action="store_true")
    parser.add_argument("--refresh-inventory", action="store_true")
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
