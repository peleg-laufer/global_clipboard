from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchored to this file, not the working directory, so the defaults are the same
# whether the server is started from the repo root, from src/, or from a container.
SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent


class Settings(BaseSettings):
    ALLOWED_SLOTS: frozenset[int] = frozenset({0, 1, 2})
    PRE_EXISTING_FILES_SLOT: int = -1
    ALLOWED_TEXT_POSITIONS: frozenset[int] = frozenset({0,1,2,3,4})
    CONNECTION_STRING: str = "mongodb://localhost:27017/"
    API_LOG_FILE_PATH: str = str(REPO_ROOT / "api_log.log")
    DB_LOG_FILE_PATH: str = str(REPO_ROOT / "db_log.log")
    DB_NAME: str = "clipboard_db"
    LOG_LEVEL: str = "DEBUG"
    FILES_PATH: str = str(REPO_ROOT / "files")
    model_config = SettingsConfigDict(env_file=SRC_DIR / ".env", env_file_encoding="utf-8")

settings = Settings()
