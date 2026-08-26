from docx import Document

from app.docx_engine import build_module, unresolved_placeholders
from app.schemas import CourseMetadata
from app.validation import audit_docx, template_compatibility
from conftest import TEMPLATE


def test_template_has_every_required_placeholder():
    assert template_compatibility(TEMPLATE) == []


def test_build_preserves_tables_and_resolves_placeholders(tmp_path, bundle):
    source = Document(TEMPLATE)
    output = build_module(TEMPLATE, tmp_path, CourseMetadata(code="AE17", title="Accounting Information System", author="Trainer"), bundle)
    built = Document(output)
    assert len(built.tables) == len(source.tables)
    assert unresolved_placeholders(output) == []
    assert audit_docx(output, expected_tables=len(source.tables))["valid"]

