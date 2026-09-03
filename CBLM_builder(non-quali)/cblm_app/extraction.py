from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from app.extraction import extract_syllabus

from .schemas import CBLMCourse, CBLMLearningOutcome, CBLMPlan, CBLMTopic


def extract_cblm_plan(path: Path, default_name: str = "") -> CBLMPlan:
    base = extract_syllabus(path)
    grouped: OrderedDict[str, list] = OrderedDict()
    fallback = base.course.outcomes[0] if base.course.outcomes else "Learning Outcome 1"
    for week in base.weeks:
        if week.type in {"orientation", "examination"}:
            continue
        key = week.learning_outcome.strip() or fallback
        grouped.setdefault(key, []).append(week)
    warnings = list(base.normalization_warnings)
    if not grouped:
        raise ValueError("No instructional learning outcomes or syllabus topics were detected")
    outcomes: list[CBLMLearningOutcome] = []
    keys = list(grouped)
    for lo_index, key in enumerate(keys, 1):
        weeks = grouped[key]
        topics = []
        for topic_index, week in enumerate(weeks, 1):
            topics.append(CBLMTopic(
                number=topic_index,
                title=week.proposed_title or week.topic_scope,
                weeks=[week.actual_week],
                resources=week.resources,
                methods=week.methods,
                guidance=week.presentation_guidance,
            ))
        week_count = len({week.actual_week for week in weeks})
        outcomes.append(CBLMLearningOutcome(
            number=lo_index,
            learning_outcome=key,
            next_learning_outcome=keys[lo_index] if lo_index < len(keys) else "",
            duration=3 * week_count,
            training_materials=list(dict.fromkeys(resource for week in weeks for resource in week.resources)),
            topics=topics,
        ))
    return CBLMPlan(
        source_filename=path.name,
        course=CBLMCourse(
            course_title=base.course.title,
            course_code=base.course.code,
            name=default_name or base.course.author,
        ),
        learning_outcomes=outcomes,
        warnings=warnings,
    )
