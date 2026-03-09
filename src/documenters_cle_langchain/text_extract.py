from __future__ import annotations

_HEADING_PREFIX: dict[str, str] = {
    "TITLE": "# ",
    "SUBTITLE": "## ",
    "HEADING_1": "# ",
    "HEADING_2": "## ",
    "HEADING_3": "### ",
    "HEADING_4": "#### ",
    "HEADING_5": "##### ",
    "HEADING_6": "###### ",
}


def extract_text(doc: dict) -> str:
    """Convert a Docs API document object to markdown-ish plain text.

    Headings are preserved as markdown headers.
    Tables become markdown tables.
    Bullet items get a leading dash.
    All other paragraphs are plain text.
    """
    parts: list[str] = []
    for element in doc.get("body", {}).get("content", []):
        if "paragraph" in element:
            line = _paragraph(element["paragraph"])
            if line:
                parts.append(line)
        elif "table" in element:
            block = _table(element["table"])
            if block:
                parts.append(block)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _paragraph(para: dict) -> str:
    style = para.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")
    bullet = para.get("bullet")

    text = "".join(
        elem.get("textRun", {}).get("content", "")
        for elem in para.get("elements", [])
    ).rstrip("\n")

    if not text.strip():
        return ""

    if bullet:
        return "- " + text
    return _HEADING_PREFIX.get(style, "") + text


def _table(table: dict) -> str:
    rows = table.get("tableRows", [])
    if not rows:
        return ""

    rendered: list[str] = []
    for i, row in enumerate(rows):
        cells = [
            " ".join(
                _paragraph(elem["paragraph"])
                for elem in cell.get("content", [])
                if "paragraph" in elem
            ).strip()
            for cell in row.get("tableCells", [])
        ]
        rendered.append("| " + " | ".join(cells) + " |")
        if i == 0:
            sep = "| " + " | ".join("---" for _ in cells) + " |"
            rendered.append(sep)

    return "\n".join(rendered)
