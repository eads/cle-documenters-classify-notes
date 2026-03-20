from documenters_cle_langchain.gsheets import _build_rows, _score_label


def _result(overrides=None):
    r = {
        "web_url": "https://example.com/doc",
        "name": "City Council Meeting",
        "date": "2026-03-01",
        "date_raw": "March 1, 2026",
        "agency": "Cleveland City Council",
        "model_used": "gpt-5-mini",
        "topics": {
            "infrastructure": {"score": 0.9, "identified": ["roads", "bridges"]},
            "schools": {"score": 0.1, "identified": []},
        },
    }
    if overrides:
        r.update(overrides)
    return r


def test_header_row():
    rows = _build_rows([_result()])
    assert rows[0] == [
        "web_url", "name", "date", "agency", "model_used",
        "infrastructure_score", "infrastructure_label", "infrastructure_identified",
        "schools_score", "schools_label", "schools_identified",
    ]


def test_data_row_values():
    rows = _build_rows([_result()])
    row = rows[1]
    assert row[0] == "https://example.com/doc"
    assert row[2] == "2026-03-01"       # date preferred over date_raw
    assert row[3] == "Cleveland City Council"
    assert row[4] == "gpt-5-mini"
    assert row[5] == 0.9                # infrastructure score
    assert row[6] == "certain"
    assert row[7] == "roads; bridges"
    assert row[8] == 0.1                # schools score
    assert row[9] == "unlikely"
    assert row[10] == ""


def test_falls_back_to_date_raw():
    rows = _build_rows([_result({"date": None})])
    assert rows[1][2] == "March 1, 2026"


def test_missing_model_used():
    r = _result()
    del r["model_used"]
    rows = _build_rows([r])
    assert rows[1][4] == ""


def test_empty_results():
    assert _build_rows([]) == []


def test_score_label_certain():
    assert _score_label(0.8) == "certain"
    assert _score_label(0.71) == "certain"


def test_score_label_unlikely():
    assert _score_label(0.2) == "unlikely"
    assert _score_label(0.29) == "unlikely"


def test_score_label_ambiguous():
    assert _score_label(0.5) == "ambiguous"
    assert _score_label(0.3) == "ambiguous"
    assert _score_label(0.7) == "ambiguous"
