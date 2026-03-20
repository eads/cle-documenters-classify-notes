"""Integration tests for Google Drive / Docs service account access.

These tests hit live Google APIs and require GOOGLE_APPLICATION_CREDENTIALS
to be set. They are skipped automatically in environments without credentials.

Test doc: https://docs.google.com/document/d/1JQpxd2g7UBnAK_ivRQi1wyECi3zSy3Sk8J19AU0LbE4/edit
- Without suggestions accepted: "Cats die many times before their deaths – Bill Shakespeare"
- With suggestions accepted:    "Cowards die many times before their deaths – William Shakespeare"
"""

import os

import pytest

from documenters_cle_langchain.gdrive import GoogleDocsClient

TEST_DOC_ID = "1JQpxd2g7UBnAK_ivRQi1wyECi3zSy3Sk8J19AU0LbE4"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds:
        pytest.skip("GOOGLE_APPLICATION_CREDENTIALS not set")
    return GoogleDocsClient(credentials_file=creds)


def test_service_account_can_fetch_doc(client):
    """Service account can access the test doc and returns non-empty text."""
    text = client.fetch_doc_text(TEST_DOC_ID)
    assert text.strip(), "Expected non-empty text from test doc"


def test_suggestions_accepted(client):
    """fetch_doc_text returns suggestion-accepted text, not original draft."""
    text = client.fetch_doc_text(TEST_DOC_ID)
    assert "Cowards" in text, (
        "Expected suggestion-accepted text ('Cowards die many times') "
        "but got original ('Cats die many times'). "
        "Check that PREVIEW_SUGGESTIONS_ACCEPTED is being used."
    )
    assert "William Shakespeare" in text, (
        "Expected 'William Shakespeare' (suggestion-accepted) "
        "but got 'Bill Shakespeare' (original)."
    )
