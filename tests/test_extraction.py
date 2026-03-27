import pytest
from documenters_cle_langchain.extraction import extract, ExtractedMeeting

# ---------------------------------------------------------------------------
# Fixtures — text patterns drawn from real docs
# ---------------------------------------------------------------------------

FULL_DOC = """\
Ward 10 Community Meeting (in-person only)
Documenter name: Tommy Oddo
Agency: Cleveland City Council
Date: March 4, 2026
See more about this meeting at Documenters.org

Summary
- Residents raised concerns about public safety.
- Two candidates introduced themselves.

### Follow-Up Questions
- How will the community respond?
- What happens to closed schools?

Notes
The meeting took place in the rectory of St. Mary's Church.

# Single Signal
Community members are alarmed about recent violence in Collinwood.
"""

NO_FOLLOWUP = """\
Budget Meeting
Documenter name: Alex Smith
Agency: City of Cleveland Urban Forestry Commission
Date: January 15, 2026
See more about this meeting at Documenters.org

Summary
The commission reviewed proposed budget cuts.

Notes
Meeting was held at City Hall.

Single Signal
Forestry budget cut by 12%.
"""

NO_SINGLE_SIGNAL = """\
Transportation Committee
Documenter name: Maria Lopez
Agency: Cleveland City Council
Date: February 3, 2026
See more about this meeting at Documenters.org

Summary
Council discussed transit funding.

### Follow-Up Questions
- Will bus routes be affected?

Notes
The meeting lasted two hours.
"""

MISSING_AGENCY = """\
Some Meeting
Documenter name: Pat Jones
Date: March 1, 2026
See more about this meeting at Documenters.org

Summary
A brief summary.

Notes
Some notes here.
"""

OUT_OF_ORDER = """\
Weird Meeting
Documenter name: Sam Green
Agency: Cuyahoga County Council
Date: March 5, 2026
See more about this meeting at Documenters.org

Notes
Notes came first for some reason.

Summary
Summary came second.

Single Signal
The signal.
"""

ALTERNATE_DATE_FORMAT = """\
Some Meeting
Documenter name: Lee Brown
Agency: Cleveland Board of Zoning Appeals
Date: 03/02/2026
See more about this meeting at Documenters.org

Summary
Variance requests were reviewed.

Notes
Board approved two variances.

Single Signal
Zoning changes approved near Clark Ave.
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _extract(text, doc_id="test-1"):
    return extract(doc_id=doc_id, text=text)


def test_full_doc_all_fields():
    result = _extract(FULL_DOC)
    assert result.meeting_name == "Ward 10 Community Meeting (in-person only)"
    assert result.documenter_name == "Tommy Oddo"
    assert result.agency == "Cleveland City Council"
    assert result.date_raw == "March 4, 2026"
    assert result.date == "2026-03-04"
    assert "public safety" in result.summary
    assert "community respond" in result.follow_up_questions
    assert "St. Mary's" in result.notes
    assert "Collinwood" in result.single_signal


def test_full_doc_high_confidence():
    result = _extract(FULL_DOC)
    assert result.confidence >= 0.75


def test_no_followup_still_parses():
    result = _extract(NO_FOLLOWUP)
    assert result.agency == "City of Cleveland Urban Forestry Commission"
    assert result.follow_up_questions == ""
    assert "budget cuts" in result.summary
    assert result.confidence >= 0.75


def test_no_single_signal():
    result = _extract(NO_SINGLE_SIGNAL)
    assert result.single_signal == ""
    assert result.confidence >= 0.75


def test_missing_agency_lowers_confidence():
    result = _extract(MISSING_AGENCY)
    assert result.agency == ""
    assert result.confidence < 1.0
    assert "agency" in result.missing_fields


def test_out_of_order_sections():
    result = _extract(OUT_OF_ORDER)
    assert "Notes came first" in result.notes
    assert "Summary came second" in result.summary
    assert result.single_signal == "The signal."


def test_alternate_date_format():
    result = _extract(ALTERNATE_DATE_FORMAT)
    assert result.date == "2026-03-02"


def test_unparseable_date_is_none():
    text = FULL_DOC.replace("Date: March 4, 2026", "Date: sometime last week")
    result = _extract(text)
    assert result.date is None
    assert result.date_raw == "sometime last week"


def test_doc_id_preserved():
    result = _extract(FULL_DOC, doc_id="abc-123")
    assert result.doc_id == "abc-123"


def test_agency_link_stripped():
    doc = FULL_DOC.replace(
        "Agency: Cleveland City Council",
        "Agency: Cleveland City Council (https://city.cleveland.gov/council)",
    )
    result = _extract(doc)
    assert result.agency == "Cleveland City Council"


def test_agency_without_link_unchanged():
    result = _extract(FULL_DOC)
    assert result.agency == "Cleveland City Council"
