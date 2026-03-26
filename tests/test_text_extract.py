from documenters_cle_langchain.text_extract import extract_text


def _doc(elements):
    return {"body": {"content": elements}}


def _paragraph(text, style="NORMAL_TEXT", bullet=False):
    para = {
        "paragraphStyle": {"namedStyleType": style},
        "elements": [{"textRun": {"content": text}}],
    }
    if bullet:
        para["bullet"] = {}
    return {"paragraph": para}


def _linked_paragraph(runs, style="NORMAL_TEXT"):
    """Build a paragraph element with mixed linked and plain runs.

    ``runs`` is a list of ``(text, url_or_None)`` tuples.
    """
    elements = []
    for text, url in runs:
        run: dict = {"content": text}
        if url:
            run["textStyle"] = {"link": {"url": url}}
        else:
            run["textStyle"] = {}
        elements.append({"textRun": run})
    return {"paragraph": {"paragraphStyle": {"namedStyleType": style}, "elements": elements}}


def _table(rows):
    return {
        "table": {
            "tableRows": [
                {
                    "tableCells": [
                        {
                            "content": [
                                _paragraph(cell)
                            ]
                        }
                        for cell in row
                    ]
                }
                for row in rows
            ]
        }
    }


def test_normal_paragraph():
    doc = _doc([_paragraph("Hello world")])
    assert extract_text(doc) == "Hello world"


def test_heading_levels():
    doc = _doc([
        _paragraph("Title", style="HEADING_1"),
        _paragraph("Subtitle", style="HEADING_2"),
        _paragraph("Section", style="HEADING_3"),
    ])
    assert extract_text(doc) == "# Title\n## Subtitle\n### Section"


def test_bullet_item():
    doc = _doc([_paragraph("Item one", bullet=True)])
    assert extract_text(doc) == "- Item one"


def test_empty_paragraphs_skipped():
    doc = _doc([
        _paragraph("First"),
        _paragraph("   "),
        _paragraph("Second"),
    ])
    assert extract_text(doc) == "First\nSecond"


def test_table():
    doc = _doc([_table([["Name", "Value"], ["Agency", "Cleveland"]])])
    result = extract_text(doc)
    lines = result.splitlines()
    assert "| Name | Value |" in lines[0]
    assert "| --- | --- |" in lines[1]
    assert "| Agency | Cleveland |" in lines[2]


def test_trailing_newline_stripped_from_runs():
    doc = _doc([_paragraph("Hello\n")])
    assert extract_text(doc) == "Hello"


def test_empty_doc():
    assert extract_text({}) == ""


# ---------------------------------------------------------------------------
# Hyperlink preservation (Issue #23)
# ---------------------------------------------------------------------------

def test_hyperlink_run_appends_url():
    doc = _doc([_linked_paragraph([("Ohio law", "https://codes.ohio.gov/ohio-revised-code/section-5321.20")])])
    assert extract_text(doc) == "Ohio law (https://codes.ohio.gov/ohio-revised-code/section-5321.20)"


def test_plain_run_unaffected():
    doc = _doc([_linked_paragraph([("plain text", None)])])
    assert extract_text(doc) == "plain text"


def test_mixed_linked_and_plain_runs():
    doc = _doc([_linked_paragraph([
        ("See ", None),
        ("Ohio law", "https://codes.ohio.gov/ohio-revised-code/section-5321.20"),
        (" for details\n", None),
    ])])
    result = extract_text(doc)
    assert result == "See Ohio law (https://codes.ohio.gov/ohio-revised-code/section-5321.20) for details"


def test_hyperlink_run_with_no_content_omits_url():
    """A linked run whose text is blank should not emit a bare URL in parens."""
    doc = _doc([_linked_paragraph([("  ", "https://example.com"), ("real text", None)])])
    assert "(https://example.com)" not in extract_text(doc)
