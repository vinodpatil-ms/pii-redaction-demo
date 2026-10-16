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
        document_intelligence_endpoint=None,
    )
    with pytest.raises(ValueError, match="APP_DOCUMENT_INTELLIGENCE_ENDPOINT"):
        build_image_pipeline(settings)


def test_build_pipelines_use_separate_endpoints_and_shared_credential() -> None:
    settings = Settings(
        _env_file=None,
        ai_services_endpoint="https://language.example.test",
        document_intelligence_endpoint="https://ocr.example.test",
    )
    credential = Mock()
    with (
        patch("pii_redaction_demo.main.AzureDocumentIntelligenceOcrProvider") as ocr,
        patch("pii_redaction_demo.main.AzureLanguagePiiProvider") as language,
    ):
        build_image_pipeline(settings, credential)
        ocr.assert_called_once_with("https://ocr.example.test", credential)
        language.assert_called_once_with("https://language.example.test", credential)

        settings.document_intelligence_endpoint = None
        build_email_pipeline(settings, credential)
        assert language.call_count == 2
        assert ocr.call_count == 1
