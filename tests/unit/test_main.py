from collections.abc import Callable
from unittest.mock import Mock, patch

import pytest

from pii_redaction_demo.core.config import Settings
from pii_redaction_demo.main import build_email_pipeline, build_image_pipeline


@pytest.mark.parametrize("build", [build_image_pipeline, build_email_pipeline])
def test_build_pipeline_requires_ai_services_endpoint(build: Callable[[Settings], object]) -> None:
    settings = Settings(_env_file=None, ai_services_endpoint=None)

    with pytest.raises(ValueError, match="APP_AI_SERVICES_ENDPOINT"):
        build(settings)


def test_image_pipeline_requires_document_intelligence_endpoint() -> None:
    settings = Settings(
        _env_file=None,
        ai_services_endpoint="https://language.example.test",
        ocr_provider="document_intelligence",
        document_intelligence_endpoint=None,
    )
    with pytest.raises(ValueError, match="APP_DOCUMENT_INTELLIGENCE_ENDPOINT"):
        build_image_pipeline(settings)


@pytest.mark.parametrize("provider", ["content_understanding", "document_intelligence"])
def test_build_pipelines_use_selected_provider_and_shared_credential(provider: str) -> None:
    settings = Settings(
        _env_file=None,
        ai_services_endpoint="https://language.example.test",
        ocr_provider=provider,
        content_understanding_endpoint="https://cu.example.test",
        document_intelligence_endpoint="https://ocr.example.test",
    )
    credential = Mock()
    with (
        patch("pii_redaction_demo.main.AzureDocumentIntelligenceOcrProvider") as di,
        patch("pii_redaction_demo.main.AzureContentUnderstandingOcrProvider") as cu,
        patch("pii_redaction_demo.main.AzureLanguagePiiProvider") as language,
    ):
        build_image_pipeline(settings, credential)
        if provider == "content_understanding":
            cu.assert_called_once_with("https://cu.example.test", credential)
            di.assert_not_called()
        else:
            di.assert_called_once_with("https://ocr.example.test", credential)
            cu.assert_not_called()
        language.assert_called_once_with("https://language.example.test", credential)

        settings.document_intelligence_endpoint = None
        settings.content_understanding_endpoint = None
        build_email_pipeline(settings, credential)
        assert language.call_count == 2
        assert cu.call_count + di.call_count == 1


def test_default_image_pipeline_requires_content_understanding_endpoint() -> None:
    settings = Settings(
        _env_file=None,
        ai_services_endpoint="https://language.example.test",
        content_understanding_endpoint=None,
        document_intelligence_endpoint="https://ocr.example.test",
    )
    with pytest.raises(ValueError, match="APP_CONTENT_UNDERSTANDING_ENDPOINT"):
        build_image_pipeline(settings)


def test_email_only_does_not_construct_either_ocr_provider() -> None:
    settings = Settings(
        _env_file=None,
        ai_services_endpoint="https://language.example.test",
        content_understanding_endpoint=None,
        document_intelligence_endpoint=None,
    )
    with (
        patch("pii_redaction_demo.main.AzureDocumentIntelligenceOcrProvider") as di,
        patch("pii_redaction_demo.main.AzureContentUnderstandingOcrProvider") as cu,
        patch("pii_redaction_demo.main.AzureLanguagePiiProvider"),
    ):
        build_email_pipeline(settings, Mock())
        di.assert_not_called()
        cu.assert_not_called()
