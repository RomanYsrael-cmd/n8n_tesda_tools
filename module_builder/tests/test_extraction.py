from app.extraction import extract_syllabus, parse_week_range, split_scope
from conftest import SYLLABUS


def test_week_range_parsing():
    assert parse_week_range("Week 5-6") == [5, 6]
    assert parse_week_range("WEEKS 15 to 17") == [15, 16, 17]
    assert parse_week_range("Week 9") == [9]
    assert parse_week_range("not a week") == []


def test_multi_week_split_has_complete_nonduplicate_parts():
    parts = split_scope("Accounting Records 1. Records 2. Documents 3. Controls", [5, 6])
    scopes = [scope for _, scope in parts]
    assert len(parts) == 2
    assert "Records" in scopes[0]
    assert "Documents" in " ".join(scopes)
    assert scopes[0] != scopes[1]


def test_ae17_default_plan():
    plan = extract_syllabus(SYLLABUS)
    skipped = [w.actual_week for w in plan.weeks if not w.generate]
    generated = [w.actual_week for w in plan.weeks if w.generate]
    assert skipped == [1, 4, 9, 13, 18]
    assert generated == [2, 3, 5, 6, 7, 8, 10, 11, 12, 14, 15, 16, 17]
    assert [w.lesson_number for w in plan.weeks if w.generate] == list(range(1, 14))
    assert len({w.topic_scope for w in plan.weeks if w.actual_week in {5, 6, 7, 8, 11, 12, 15, 16, 17}}) == 9

