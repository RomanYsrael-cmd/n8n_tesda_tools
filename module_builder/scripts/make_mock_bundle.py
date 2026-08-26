"""Create deterministic schema-valid mock content for local smoke tests only."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.schemas import ApplyContent, Choice, ModuleBundle, NormalizedSyllabus, PresentationBlock, PresentationContent, QuizContent, QuizQuestion, RichTextSpan


def main(job_id: str, output: Path):
    con = sqlite3.connect("/data/module-builder.sqlite3")
    row = con.execute("SELECT normalized_json FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise SystemExit("Job not found")
    plan = NormalizedSyllabus.model_validate_json(row[0])
    modules = []
    for week in [w for w in plan.weeks if w.generate]:
        questions = []
        key = {}
        answer_pattern = ["A", "B", "D", "C", "B", "A", "C", "D", "A", "B"]
        for i in range(1, 11):
            qid = f"Q{i}"
            answer = answer_pattern[i - 1]
            choices = {letter: f"Incorrect alternative {letter} for item {i}" for letter in "ABCD"}
            choices[answer] = "It supports accurate processing and decisions"
            questions.append(QuizQuestion(id=qid, question=f"Which business data statement is correct for AIS concept {i}?", choices=[Choice(id=letter, text=choices[letter]) for letter in "ABCD"], answer=answer))
            key[qid] = answer
        bundle = ModuleBundle(
            actual_week=week.actual_week,
            lesson_number=week.lesson_number,
            approved_scope=week.topic_scope,
            presentation=PresentationContent(
                lesson_title=week.proposed_title.replace(" |", "").strip(),
                information_sheet_title=f"Key Facts {week.lesson_number}.1 – {week.proposed_title}",
                measurable_objectives=["Explain the essential concepts accurately", "Apply the concepts to a realistic business case"],
                pre_assessment=["What do you already know about this lesson's main ideas?"],
                introduction=" ".join(["This information sheet introduces the approved weekly concepts through clear explanations and realistic accounting information system examples for beginning learners."] * 4),
                presentation=[PresentationBlock(type="heading", spans=[RichTextSpan(text="Core concepts")]), PresentationBlock(type="paragraph", spans=[RichTextSpan(text=f"This lesson examines {week.topic_scope}. " + " ".join(["Accounting information systems support accurate processing informed decisions reliable records and responsible organizational operations in realistic workplace situations."] * 55))]), PresentationBlock(type="example", spans=[RichTextSpan(text="A small business records a transaction, checks the source document, updates the ledger, and reviews the resulting report.", italic=True)])],
                references=[],
            ),
            quiz=QuizContent(questions=questions, answer_key=key),
            practical_activity=ApplyContent(
                title="Produce a practical AIS output",
                performance_objective="Create a complete and accurate output that demonstrates the lesson concepts.",
                supplies_materials=["Case worksheet", "Reference data"],
                equipment=["Computer"],
                steps=["Read the business case", "Identify the required inputs", "Perform the required processing", "Prepare the expected output", "Check and submit the completed output"],
                assessment_method="Direct observation and review of the completed output",
                performance_criteria=["Identifies all required inputs", "Uses the correct processing sequence", "Produces an accurate output", "Keeps the output aligned to the business case", "Submits a complete and readable final result"],
            ),
        )
        modules.append(bundle.model_dump())
    output.write_text(json.dumps({"modules": modules}, indent=2), encoding="utf-8")
    print(f"Wrote {len(modules)} mock modules to {output}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
