"""conftest.py — pytest configuration for documenters-cle-langchain tests.

Auto-skips integration tests when OPENAI_API_KEY is absent so the full
test suite runs cleanly in CI without any API credentials.
"""
from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip integration tests when OPENAI_API_KEY is absent."""
    if os.getenv("OPENAI_API_KEY"):
        return
    skip_marker = pytest.mark.skip(
        reason="OPENAI_API_KEY not set — skipping integration tests"
    )
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip_marker)
