import pytest
from pydantic import ValidationError

from pii_redaction_demo.core.config import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_services_endpoint is None
    assert settings.document_intelligence_endpoint is None
    assert settings.content_understanding_endpoint is None
    assert settings.ocr_provider == "content_understanding"
    assert settings.pii_language == "en"
    assert settings.pii_min_confidence == 0.0


def test_settings_load_document_intelligence_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("APP_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://ocr.example.test")
    assert Settings(_env_file=None).document_intelligence_endpoint == "https://ocr.example.test"


def test_settings_load_content_understanding_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("APP_CONTENT_UNDERSTANDING_ENDPOINT", "https://cu.example.test")
    assert Settings(_env_file=None).content_understanding_endpoint == "https://cu.example.test"


def test_settings_select_document_intelligence_and_reject_unknown_provider(monkeypatch) -> None:
    monkeypatch.setenv("APP_OCR_PROVIDER", "document_intelligence")
    assert Settings(_env_file=None).ocr_provider == "document_intelligence"
    monkeypatch.setenv("APP_OCR_PROVIDER", "unsupported")
    with pytest.raises(ValidationError, match="ocr_provider"):
        Settings(_env_file=None)
