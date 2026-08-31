from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    log_level: str = "INFO"
    ai_services_endpoint: str | None = None
    pii_language: str = "en"
    # 0.0 masks every detection Azure AI Language returns; raise it to drop weak matches.
    pii_min_confidence: float = 0.0
    input_images_dir: str = "input-images"
    output_images_dir: str = "output-images"
    input_emails_dir: str = "input-emails"
    output_emails_dir: str = "output-emails"
    trace_dir: str = "data/processed"

    # Anchored to the repo root so the file loads regardless of the working directory.
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", ".env"),
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
