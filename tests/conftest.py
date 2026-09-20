import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient

from clip_api import api
from constants import settings

TEST_DB_NAME = "clipboard_test_db"


@pytest.fixture
def client(monkeypatch, tmp_path):
    """A TestClient pointed at a clean test DB and a temp files folder."""

    # 1. point settings at the test database, not the real one
    monkeypatch.setattr(settings, "DB_NAME", TEST_DB_NAME)

    # 2. point file storage at a temp folder for this test only
    monkeypatch.setattr(settings, "FILES_PATH", str(tmp_path / "files"))

    # 3. keep test runs from overwriting your real log files
    monkeypatch.setattr(settings, "DB_LOG_FILE_PATH", str(tmp_path / "db.log"))
    monkeypatch.setattr(settings, "API_LOG_FILE_PATH", str(tmp_path / "api.log"))

    # 4. start clean - drop anything left over from a previous run
    admin = MongoClient(settings.CONNECTION_STRING)
    admin.drop_database(TEST_DB_NAME)

    # 5. `with` runs lifespan, which runs connect_to_db on the right loop
    with TestClient(api) as test_client:
        yield test_client          # the test runs here

    # 6. teardown - runs even if the test failed
    admin.drop_database(TEST_DB_NAME)
    admin.close()
