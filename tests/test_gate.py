from documenters_cle_langchain.gate import passes_extraction_gate
from documenters_cle_langchain.extraction import ExtractedMeeting


def _result(missing=()):
    return ExtractedMeeting(
        doc_id="x", meeting_name="Test", documenter_name="A",
        agency="Agency" if "agency" not in missing else "",
        date_raw="March 1, 2026" if "date" not in missing else "",
        date="2026-03-01" if "date" not in missing else None,
        documenters_url="", summary="text" if "summary" not in missing else "",
        follow_up_questions="", notes="notes" if "notes" not in missing else "",
        single_signal="", confidence=(4 - len(missing)) / 4,
        missing_fields=missing,
    )


def test_all_fields_passes():
    assert passes_extraction_gate(_result()) is True


def test_missing_agency_fails():
    assert passes_extraction_gate(_result(missing=("agency",))) is False


def test_missing_multiple_fails():
    assert passes_extraction_gate(_result(missing=("agency", "date"))) is False
