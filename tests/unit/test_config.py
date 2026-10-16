from pii_redaction_demo.core.config import Settings


def test_settings_use_safe_local_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_services_endpoint is None
    assert settings.document_intelligence_endpoint is None
    assert settings.pii_language == "en"
    assert settings.pii_min_confidence == 0.0


def test_settings_load_document_intelligence_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("APP_DOCUMENT_INTELLIGENCE_ENDPOINT", "https://ocr.example.test")
    assert Settings(_env_file=None).document_intelligence_endpoint == "https://ocr.example.test"
