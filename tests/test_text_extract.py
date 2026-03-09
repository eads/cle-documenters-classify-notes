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
