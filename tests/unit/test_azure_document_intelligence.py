from unittest.mock import Mock, patch

import pytest
from azure.ai.documentintelligence.models import (
    AnalyzeResult,
    DocumentLine,
    DocumentPage,
    DocumentSpan,
    DocumentWord,
)
from azure.core.exceptions import HttpResponseError

from pii_redaction_demo.providers.azure_document_intelligence import (
    AzureDocumentIntelligenceOcrProvider,
    _to_ocr_result,
    _to_polygon,
)


def _result() -> AnalyzeResult:
    return AnalyzeResult(
        api_version="2024-11-30",
        model_id="prebuilt-read",
        string_index_type="unicodeCodePoint",
        content="Jane Doe\nJane",
        pages=[
            DocumentPage(
                page_number=1,
                width=100,
                height=100,
                unit="pixel",
                spans=[DocumentSpan(offset=0, length=13)],
                lines=[
                    DocumentLine(
                        content="Jane Doe",
                        polygon=[0, 0, 80, 0, 80, 10, 0, 10],
                        spans=[DocumentSpan(offset=0, length=8)],
                    ),
                    DocumentLine(
                        content="Jane",
                        polygon=[0, 20, 40, 20, 40, 30, 0, 30],
                        spans=[DocumentSpan(offset=9, length=4)],
                    ),
                ],
                words=[
                    DocumentWord(
                        content="Doe",
                        polygon=[50, 0, 80, 0, 80, 10, 50, 10],
                        span=DocumentSpan(offset=5, length=3),
                        confidence=0.99,
                    ),
                    DocumentWord(
                        content="Jane",
                        polygon=[0, 20, 40, 20, 40, 30, 0, 30],
                        span=DocumentSpan(offset=9, length=4),
                        confidence=0.99,
                    ),
                    DocumentWord(
                        content="Jane",
                        polygon=[0, 0, 40, 0, 40, 10, 0, 10],
                        span=DocumentSpan(offset=0, length=4),
                        confidence=0.99,
                    ),
                ],
            )
        ],
    )


def test_maps_words_to_lines_by_span_in_reading_order() -> None:
    result = _to_ocr_result(_result())

    assert result.text == "Jane Doe\nJane"
    assert [word.text for word in result.regions[0].words] == ["Jane", "Doe"]
    assert result.regions[0].words[0].polygon == ((0, 0), (40, 0), (40, 10), (0, 10))
    assert result.regions[1].words[0].polygon == ((0, 20), (40, 20), (40, 30), (0, 30))
    assert result.model_version is None


def test_provider_uses_ga_read_api_waits_for_result_and_closes() -> None:
    with patch(
        "pii_redaction_demo.providers.azure_document_intelligence.DocumentIntelligenceClient"
    ) as client_type:
        client = client_type.return_value
        client.begin_analyze_document.return_value.result.return_value = _result()
        credential = Mock()
        provider = AzureDocumentIntelligenceOcrProvider("https://example.test", credential)

        result = provider.read_image(b"image-bytes")
        provider.close()

        client_type.assert_called_once_with(
            endpoint="https://example.test", credential=credential, api_version="2024-11-30"
        )
        args, kwargs = client.begin_analyze_document.call_args
        assert args == ("prebuilt-read",)
        assert kwargs["body"].read() == b"image-bytes"
        assert kwargs["content_type"] == "application/octet-stream"
        assert kwargs["string_index_type"] == "unicodeCodePoint"
        client.begin_analyze_document.return_value.result.assert_called_once_with()
        client.close.assert_called_once_with()
        assert result.text == "Jane Doe\nJane"


def test_provider_defaults_to_entra_credential_and_propagates_poll_failure() -> None:
    with (
        patch(
            "pii_redaction_demo.providers.azure_document_intelligence.DocumentIntelligenceClient"
        ) as client_type,
        patch(
            "pii_redaction_demo.providers.azure_document_intelligence.DefaultAzureCredential"
        ) as credential_type,
    ):
        client_type.return_value.begin_analyze_document.return_value.result.side_effect = (
            HttpResponseError("OCR failed")
        )
        provider = AzureDocumentIntelligenceOcrProvider("https://example.test")

        with pytest.raises(HttpResponseError, match="OCR failed"):
            provider.read_image(b"image")

        assert client_type.call_args.kwargs["credential"] is credential_type.return_value


def test_empty_ocr_returns_empty_text() -> None:
    result = _result()
    result.pages[0].lines = None
    result.pages[0].words = None
    assert _to_ocr_result(result).text == ""
    result.pages = []
    assert _to_ocr_result(result).regions == ()


def test_line_without_words_retains_line_polygon() -> None:
    result = _result()
    result.pages[0].words = None
    converted = _to_ocr_result(result)
    assert converted.regions[0].words == ()
    assert converted.regions[0].polygon == ((0, 0), (80, 0), (80, 10), (0, 10))


def test_rejects_multiple_pages_and_non_pixel_coordinates() -> None:
    result = _result()
    result.pages.append(result.pages[0])
    with pytest.raises(ValueError, match="single-page"):
        _to_ocr_result(result)
    result.pages.pop()
    result.pages[0].unit = "inch"
    with pytest.raises(ValueError, match="pixels"):
        _to_ocr_result(result)


def test_polygon_conversion_handles_fractions_and_missing_coordinates() -> None:
    assert _to_polygon([1.2, 2.8, 9.7, 10.1]) == ((1, 3), (10, 10))
    assert _to_polygon(None) == ()
    with pytest.raises(ValueError):
        _to_polygon([1, 2, 3])
