import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ALLOWED_SLOTS: frozenset[int] = frozenset({0, 1, 2})
    PRE_EXISTING_FILES_SLOT: int = -1
    ALLOWED_TEXT_POSITIONS: frozenset[int] = frozenset({0,1,2,3,4})
    CONNECTION_STRING: str = "mongodb://localhost:27017/"
    API_LOG_FILE_PATH: str = "api_log.log"
    DB_LOG_FILE_PATH: str = "db_log.log"
    DB_NAME: str = "clipboard_db"
    LOG_LEVEL: str = "DEBUG"
    FILES_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")
    model_config = SettingsConfigDict(env_file="src/.env", env_file_encoding="utf-8")
    
settings = Settings()