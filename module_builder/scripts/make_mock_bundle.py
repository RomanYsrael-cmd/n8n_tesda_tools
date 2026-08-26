"""Create deterministic schema-valid mock content for local smoke tests only."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from app.schemas import ApplyContent, Choice, ModuleBundle, NormalizedSyllabus, PresentationContent, QuizContent, QuizQuestion


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
        for i in range(1, 11):
            qid = f"Q{i}"
            questions.append(QuizQuestion(id=qid, question=f"Which business data statement is correct for approved AIS concept {i}?", choices=[Choice(id="A", text="It supports accurate processing and decisions"), Choice(id="B", text="It removes all source documents"), Choice(id="C", text="It guarantees that no error can occur"), Choice(id="D", text="It replaces every management decision")], answer="A"))
            key[qid] = "A"
        bundle = ModuleBundle(
            actual_week=week.actual_week,
            lesson_number=week.lesson_number,
            approved_scope=week.topic_scope,
            presentation=PresentationContent(
                lesson_title=week.proposed_title.replace(" |", "").strip(),
                information_sheet_title=f"Key Facts {week.lesson_number}.1 – {week.proposed_title}",
                measurable_objectives=["Explain the approved concepts accurately", "Apply the approved concepts to a realistic business case"],
                pre_assessment=["What do you already know about this lesson's approved scope?"],
                introduction=" ".join(["This information sheet introduces the approved weekly concepts through clear explanations and realistic accounting information system examples for beginning learners."] * 4),
                presentation=[f"The approved scope is {week.topic_scope}. " + " ".join(["Accounting information systems support accurate processing informed decisions reliable records and responsible organizational operations in realistic workplace situations."] * 55)],
            ),
            quiz=QuizContent(questions=questions, answer_key=key),
            practical_activity=ApplyContent(
                title="Produce an approved-scope AIS output",
                performance_objective="Create a complete and accurate output that demonstrates the approved weekly scope.",
                supplies_materials=["Case worksheet", "Reference data"],
                equipment=["Computer"],
                steps=["Read the case and approved scope", "Identify the required inputs", "Perform the required processing", "Prepare the expected output", "Check and submit the completed output"],
                assessment_method="Direct observation and review of the completed output",
                performance_criteria=["Identifies all required inputs", "Uses the correct processing sequence", "Produces an accurate output", "Keeps the output aligned to the approved scope", "Submits a complete and readable final result"],
            ),
        )
        modules.append(bundle.model_dump())
    output.write_text(json.dumps({"modules": modules}, indent=2), encoding="utf-8")
    print(f"Wrote {len(modules)} mock modules to {output}")


if __name__ == "__main__":
    main(sys.argv[1], Path(sys.argv[2]))
