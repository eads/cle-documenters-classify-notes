import json
import pytest
from pathlib import Path
from documenters_cle_langchain.manifest import load_manifest


def _write(tmp_path, data):
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(data))
    return p


def test_load_basic(tmp_path):
    p = _write(tmp_path, [{"doc_id": "abc", "text": "hello", "name": "Test Doc", "web_url": "https://example.com"}])
    docs = load_manifest(p)
    assert len(docs) == 1
    assert docs[0].doc_id == "abc"
    assert docs[0].text == "hello"


def test_missing_doc_id_uses_row_index(tmp_path):
    p = _write(tmp_path, [{"text": "no id here"}])
    docs = load_manifest(p)
    assert docs[0].doc_id == "row-0"


def test_extra_fields_ignored(tmp_path):
    p = _write(tmp_path, [{"doc_id": "x", "text": "t", "unknown_field": "ignored"}])
    docs = load_manifest(p)
    assert len(docs) == 1


def test_file_not_found():
    with pytest.raises(FileNotFoundError):
        load_manifest(Path("/nonexistent/manifest.json"))


def test_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("not json {{{")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_manifest(p)


def test_not_a_list(tmp_path):
    p = _write(tmp_path, {"doc_id": "x"})
    with pytest.raises(ValueError, match="array"):
        load_manifest(p)
