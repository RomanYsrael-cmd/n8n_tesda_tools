from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ApplyContent, Choice, ContentReference, PresentationBlock, QuizContent, QuizQuestion, RichTextSpan

RESPONSE_START = "RESPONSE-START-PQOWIEUR"
RESPONSE_END = "RESPONSE-END-PQOWIEUR"


def extract_marked_response(text: str) -> str:
    """Extract requested content while ignoring text outside the markers."""
    start = text.find(RESPONSE_START)
    end = text.find(RESPONSE_END, start + len(RESPONSE_START)) if start >= 0 else -1
    if start < 0 or end < 0:
        missing = []
        if start < 0:
            missing.append(RESPONSE_START)
        if end < 0:
            missing.append(RESPONSE_END)
        raise ValueError("response is missing required marker(s): " + ", ".join(missing))
    value = text[start + len(RESPONSE_START):end].strip()
    if not value:
        raise ValueError("response markers contain no content")
    return value


class ContentParseError(ValueError):
    pass


@dataclass
class PresentationDraft:
    objectives: list[str]
    blocks: list[PresentationBlock]
    references: list[ContentReference]


def _clean_fences(text: str) -> str:
    value = text.strip().lstrip("\ufeff")
    if value.startswith("```"):
        value = value.split("\n", 1)[1] if "\n" in value else ""
        if value.rstrip().endswith("```"):
            value = value.rstrip()[:-3]
    return value.strip()


def inline_spans(text: str) -> list[RichTextSpan]:
    text = re.sub(r"!?\[([^]]+)]\(([^)]+)\)", r"\1 (\2)", text.strip())
    spans: list[RichTextSpan] = []
    position = 0
    pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|(?<!\*)\*[^*]+?\*(?!\*)|(?<!_)_[^_]+?_(?!_))")
    for match in pattern.finditer(text):
        if match.start() > position:
            spans.append(RichTextSpan(text=text[position:match.start()]))
        token = match.group(0)
        bold = token.startswith(("**", "__"))
        spans.append(RichTextSpan(text=token[2:-2] if bold else token[1:-1], bold=bold, italic=not bold))
        position = match.end()
    if position < len(text):
        spans.append(RichTextSpan(text=text[position:]))
    return [span for span in spans if span.text] or [RichTextSpan(text=" ")]


def parse_presentation_markdown(text: str) -> PresentationDraft:
    lines = _clean_fences(text).splitlines()
    blocks: list[PresentationBlock] = []
    objectives: list[str] = []
    references: list[ContentReference] = []
    section = ""
    paragraph: list[str] = []

    def flush():
        if paragraph:
            blocks.append(PresentationBlock(type="paragraph", spans=inline_spans(" ".join(paragraph))))
            paragraph.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush(); continue
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        if heading:
            flush(); title = heading.group(1).strip(); section = title.casefold()
            if "learning objective" not in section and section not in {"references", "reference"}:
                blocks.append(PresentationBlock(type="heading", spans=inline_spans(title)))
            continue
        item = re.match(r"^[-*+]\s+(.+)$", line)
        numbered = re.match(r"^\d+[.)]\s+(.+)$", line)
        value = (item or numbered).group(1).strip() if item or numbered else ""
        if "learning objective" in section and (item or numbered):
            objectives.append(re.sub(r"[*_`]", "", value)); continue
        if section in {"references", "reference"} and (item or numbered):
            references.append(ContentReference(title=re.sub(r"[*_`]", "", value))); continue
        if item or numbered:
            flush(); blocks.append(PresentationBlock(type="numbered" if numbered else "bullet", spans=inline_spans(value))); continue
        quote = re.match(r"^>\s*(.+)$", line)
        if quote:
            flush(); value = quote.group(1).strip()
            kind = "note" if value.casefold().startswith("note:") else "example"
            value = re.sub(r"^(?:note|example|realistic example)\s*:\s*", "", value, flags=re.I)
            blocks.append(PresentationBlock(type=kind, spans=inline_spans(value))); continue
        paragraph.append(line)
    flush()
    cleaned: list[PresentationBlock] = []
    seen_headings: set[str] = set()
    for block in blocks:
        normalized = block.plain_text.strip().rstrip(":").casefold()
        if block.type == "heading":
            if normalized in seen_headings:
                continue
            seen_headings.add(normalized)
        elif cleaned and cleaned[-1].type == "heading":
            heading_text = cleaned[-1].plain_text.strip().rstrip(":").casefold()
            if normalized == heading_text:
                continue
            if block.spans and block.spans[0].text.strip().rstrip(":").casefold() == heading_text:
                remaining = block.spans[1:]
                if remaining:
                    block = block.model_copy(update={"spans": remaining})
                else:
                    continue
        cleaned.append(block)
    blocks = cleaned
    if not blocks:
        raise ContentParseError("The Markdown presentation contains no instructional sections")
    return PresentationDraft(objectives, blocks, references)


def parse_introduction(text: str) -> str:
    value = re.sub(r"^#+\s+.*$", "", _clean_fences(text), flags=re.M).strip()
    value = re.sub(r"[*_`]", "", value)
    if not value:
        raise ContentParseError("Introduction must contain readable text")
    return value


def parse_preassessment(text: str) -> list[str]:
    value = _clean_fences(text)
    items = [re.sub(r"^\s*(?:[-*+] |\d+[.)]\s+)", "", line).strip() for line in value.splitlines() if re.match(r"^\s*(?:[-*+] |\d+[.)]\s+)", line)]
    if not items:
        items = [part.strip() for part in re.split(r"(?<=[?])\s+", re.sub(r"[*_`]", "", value)) if part.strip()]
    if not items:
        raise ContentParseError("Pre-assessment must contain at least one focused question")
    return items


def _headed_sections(text: str, headers: list[str]) -> dict[str, list[str]]:
    sections = {header: [] for header in headers}; current = None
    aliases = {
        "let's apply activity": "Title of Activity",
        "lets apply activity": "Title of Activity",
        "hands-on activity": "Title of Activity",
        "hands on activity": "Title of Activity",
    }
    candidates = [(header, header) for header in headers]
    candidates.extend((alias, canonical) for alias, canonical in aliases.items() if canonical in sections)
    for raw in _clean_fences(text).splitlines():
        line = re.sub(r"^#{1,6}\s*", "", raw.strip()).strip()
        line = re.sub(r"^\d+[.)]\s*", "", line)
        line = line.strip("*_` ")
        matched = None
        remainder = ""
        for label, header in sorted(candidates, key=lambda item: len(item[0]), reverse=True):
            match = re.match(rf"^{re.escape(label)}\s*(?::|[-–—])?\s*(.*)$", line, flags=re.I)
            if match:
                matched = header
                remainder = match.group(1).strip("*_` ")
                break
        if matched:
            current = matched
            if remainder:
                sections[current].append(remainder)
            continue
        if current and line:
            sections[current].append(line)
    missing = [header for header, values in sections.items() if not values and header != "List of Equipment"]
    if missing:
        raise ContentParseError("Missing or empty exact headers: " + ", ".join(missing))
    return sections


def _list_values(lines: list[str]) -> list[str]:
    return [re.sub(r"^(?:[-*+] |\d+[.)]\s+)", "", line).strip() for line in lines if line.strip()]


def parse_apply_markdown(text: str) -> ApplyContent:
    headers = ["Title of Activity", "Performance Objective", "List of Supplies", "List of Equipment", "Steps", "Assessment Method", "Performance Criteria"]
    s = _headed_sections(text, headers)
    criteria = _list_values(s["Performance Criteria"])
    if len(criteria) < 5:
        raise ContentParseError(f"Performance Criteria must contain exactly five items; received {len(criteria)}")
    criteria = criteria[:5]
    method_text = " ".join(_list_values(s["Assessment Method"])).strip()
    allowed = ["Written examination", "Written test/quiz", "Oral questioning", "Oral examination", "Interview", "Case study", "Case problem/problem-solving", "Practical demonstration", "Direct observation", "Demonstration with oral questioning", "Observation with questioning", "Work project/practical project", "Work sample/output", "Portfolio", "Portfolio with interview", "Third-party report", "Submission of work projects/work samples"]
    # Providers sometimes embed an approved method in natural prose, such as
    # "Direct observation and group presentation evaluation." Extract only
    # canonical approved values so harmless filler does not trigger a retry.
    methods = []
    occupied: list[tuple[int, int]] = []
    for canonical in sorted(allowed, key=len, reverse=True):
        match = re.search(re.escape(canonical), method_text, flags=re.I)
        if match and not any(match.start() < end and start < match.end() for start, end in occupied):
            methods.append((match.start(), canonical))
            occupied.append(match.span())
    methods = [canonical for _, canonical in sorted(methods)]
    if not methods:
        raise ContentParseError("Assessment Method must include at least one approved method; received: " + method_text)
    return ApplyContent(title=" ".join(s["Title of Activity"]), performance_objective=" ".join(s["Performance Objective"]), supplies_materials=_list_values(s["List of Supplies"]), equipment=_list_values(s["List of Equipment"]), steps=_list_values(s["Steps"]), assessment_method="; ".join(methods), performance_criteria=criteria)


def parse_aiken_quiz(text: str) -> QuizContent:
    value = _clean_fences(text)
    parsed = []
    for block in re.split(r"\r?\n[ \t]*\r?\n", value.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        # Some local models add a harmless label before each Aiken stem even
        # when asked not to. Remove only known standalone labels; the actual
        # question, four choices, and ANSWER line remain unchanged.
        if lines and re.fullmatch(r"(?:question(?:\s+text)?|questions?)\s*:?", lines[0], flags=re.I):
            lines = lines[1:]
        if len(lines) != 6:
            continue
        choices = [re.fullmatch(fr"{letter}[.)][ \t]*(.+)", lines[index], flags=re.I)
                   for index, letter in enumerate("ABCD", 1)]
        answer = re.fullmatch(r"ANSWER:[ \t]*([ABCD])", lines[5], flags=re.I)
        if all(choices) and answer:
            parsed.append((lines[0], *(choice.group(1) for choice in choices), answer.group(1)))
    usable = []
    seen_stems: set[str] = set()
    for row in parsed:
        stem = re.sub(r"^\s*\d+[.)]\s+", "", row[0]).strip()
        normalized_stem = re.sub(r"\W+", " ", stem.casefold()).strip()
        choice_texts = [row[offset].strip().casefold() for offset in range(1, 5)]
        if not normalized_stem or normalized_stem in seen_stems or len(set(choice_texts)) != 4:
            continue
        seen_stems.add(normalized_stem)
        usable.append((stem, *row[1:]))
        if len(usable) == 10:
            break
    if len(usable) < 10:
        raise ContentParseError(f"Self Check must contain at least 10 unique valid Aiken questions; received {len(usable)}")
    parsed = usable
    # Local models often put nearly every correct response under the same
    # letter. Repositioning an existing correct choice is deterministic and
    # preserves its meaning while producing a reader-friendly answer key.
    target_answers = ("B", "D", "A", "C", "C", "A", "D", "B", "A", "C")
    questions = []
    answer_key = {}
    for index, row in enumerate(parsed, 1):
        stem = row[0].strip()
        qid = f"Q{index}"
        supplied_answer = row[5].upper()
        supplied_choices = {letter: row[offset].strip() for offset, letter in enumerate("ABCD", 1)}
        answer = target_answers[index - 1]
        correct_text = supplied_choices[supplied_answer]
        distractors = [supplied_choices[letter] for letter in "ABCD" if letter != supplied_answer]
        reordered = {}
        distractor_index = 0
        for letter in "ABCD":
            if letter == answer:
                reordered[letter] = correct_text
            else:
                reordered[letter] = distractors[distractor_index]
                distractor_index += 1
        choices = [Choice(id=letter, text=reordered[letter]) for letter in "ABCD"]
        questions.append(QuizQuestion(id=qid, question=stem, choices=choices, answer=answer)); answer_key[qid] = answer
    return QuizContent(questions=questions, answer_key=answer_key)
