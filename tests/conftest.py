"""Workspace-only temp directories; compatible with managed Windows ACLs."""
from pathlib import Path
import uuid
import pytest


@pytest.fixture
def tmp_path():
    path=Path(__file__).resolve().parents[1]/"work"/"tests"/uuid.uuid4().hex
    path.mkdir(parents=True)
    return path
