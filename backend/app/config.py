from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./linecheck.db"
    storage_dir: Path = Path("./data/images")
    secret_key: str = ""
    token_expiry_minutes: int = 60
    max_upload_bytes: int = 10_000_000
    development_mode: bool = True

settings = Settings()
