from documenters_cle_langchain.dedup import deduplicate
from documenters_cle_langchain.manifest import ManifestDocument


def _doc(doc_id, name, folder_path="2026/March/03-04-2026", text="some text",
         modified_time="2026-03-04T10:00:00Z", checksum=None):
    return ManifestDocument(
        doc_id=doc_id,
        name=name,
        folder_path=folder_path,
        modified_time=modified_time,
        text=text,
        text_checksum=checksum or f"checksum-{doc_id}",
    )


def test_no_duplicates_unchanged():
    docs = [
        _doc("1", "Agency Meeting 03/04/2026"),
        _doc("2", "Other Agency Meeting 03/04/2026", folder_path="2026/March/03-05-2026"),
    ]
    result = deduplicate(docs)
    assert len(result) == 2


def test_identical_checksum_keeps_most_recent():
    docs = [
        _doc("1", "Meeting A", text="same", modified_time="2026-03-01T10:00:00Z", checksum="abc"),
        _doc("2", "Meeting A copy", text="same", modified_time="2026-03-04T10:00:00Z", checksum="abc"),
    ]
    result = deduplicate(docs)
    assert len(result) == 1
    assert result[0].doc_id == "2"


def test_name_containment_keeps_most_recent():
    docs = [
        _doc("1", "Agency Board Meeting 03/02/2026", modified_time="2026-03-01T09:00:00Z"),
        _doc("2", "Copy of Agency Board Meeting 03/02/2026", modified_time="2026-03-02T15:00:00Z"),
        _doc("3", "Adam Joseph Copy of Agency Board Meeting 03/02/2026", modified_time="2026-03-01T08:00:00Z"),
    ]
    result = deduplicate(docs)
    assert len(result) == 1
    assert result[0].doc_id == "2"


def test_name_containment_scoped_to_folder():
    docs = [
        _doc("1", "Agency Meeting 03/02/2026", folder_path="2026/March/03-02-2026"),
        _doc("2", "Copy of Agency Meeting 03/02/2026", folder_path="2026/March/03-02-2026"),
        _doc("3", "Agency Meeting 03/05/2026", folder_path="2026/March/03-05-2026"),
    ]
    result = deduplicate(docs)
    assert len(result) == 2
    ids = {d.doc_id for d in result}
    assert "3" in ids


def test_single_doc_unchanged():
    docs = [_doc("1", "Solo Meeting")]
    result = deduplicate(docs)
    assert len(result) == 1
    assert result[0].doc_id == "1"
