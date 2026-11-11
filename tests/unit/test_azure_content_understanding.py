import io
import json
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import (
    AnalysisResult,
    ContentSpan,
    DocumentContent,
    DocumentLine,
    DocumentPage,
    DocumentWord,
)
from azure.core.credentials import AccessToken, TokenCredential
from azure.core.exceptions import HttpResponseError
from azure.core.pipeline.transport import HttpRequest, HttpResponse, HttpTransport
from azure.core.utils import CaseInsensitiveDict
from PIL import Image

from pii_redaction_demo.domain.models import PiiEntity, RedactionResult
from pii_redaction_demo.providers.azure_content_understanding import (
    AzureContentUnderstandingOcrProvider,
    _to_ocr_result,
    _to_polygon,
)
from pii_redaction_demo.providers.pillow_image import PillowImageRedactor
from pii_redaction_demo.services.pii_redaction import PiiRedactionService
from pii_redaction_demo.services.pipeline import ImageRedactionPipeline


def _content() -> DocumentContent:
    return DocumentContent(
        start_page_number=1,
        end_page_number=1,
        unit="pixel",
        markdown="Jane Doe\nJane",
        pages=[
            DocumentPage(
                page_number=1,
                width=100,
                height=100,
                lines=[
                    DocumentLine(
                        content="Jane Doe",
                        source="D(1,0,0,80,0,80,10,0,10)",
                        span=ContentSpan(offset=0, length=8),
                    ),
                    DocumentLine(
                        content="Jane",
                        source="D(1,0,20,40,20,40,30,0,30)",
                        span=ContentSpan(offset=9, length=4),
                    ),
                ],
                words=[
                    DocumentWord(
                        content="Doe",
                        source="D(1,50,0,80,0,80,10,50,10)",
                        span=ContentSpan(offset=5, length=3),
                    ),
                    DocumentWord(
                        content="Jane",
                        source="D(1,0,20,40,20,40,30,0,30)",
                        span=ContentSpan(offset=9, length=4),
                    ),
                    DocumentWord(
                        content="Jane",
                        source="D(1,0,0,40,0,40,10,0,10)",
                        span=ContentSpan(offset=0, length=4),
                    ),
                ],
            )
        ],
    )


def _result(content: DocumentContent | None = None) -> AnalysisResult:
    return AnalysisResult(
        api_version="2025-11-01",
        analyzer_id="prebuilt-read",
        string_encoding="codePoint",
        contents=[content if content is not None else _content()],
    )


def test_maps_words_and_lines_in_span_order_without_using_generated_markdown() -> None:
    content = _content()
    content.markdown = "# Jane Doe\n\nJane"
    content.pages[0].lines.reverse()
    result = _to_ocr_result(_result(content))

    assert result.text == "Jane Doe\nJane"
    assert [word.text for word in result.regions[0].words] == ["Jane", "Doe"]
    assert result.regions[0].words[0].polygon == ((0, 0), (40, 0), (40, 10), (0, 10))
    assert result.regions[1].words[0].polygon == ((0, 20), (40, 20), (40, 30), (0, 30))
    assert result.model_version is None


def test_provider_uses_ga_read_binary_api_waits_and_closes() -> None:
    with patch(
        "pii_redaction_demo.providers.azure_content_understanding.ContentUnderstandingClient"
    ) as client_type:
        client = client_type.return_value
        client.begin_analyze_binary.return_value.result.return_value = _result()
        credential = Mock()
        provider = AzureContentUnderstandingOcrProvider("https://example.test", credential)

        result = provider.read_image(b"image-bytes")
        provider.close()

        client_type.assert_called_once_with(
            endpoint="https://example.test", credential=credential, api_version="2025-11-01"
        )
        client.begin_analyze_binary.assert_called_once_with(
            "prebuilt-read", b"image-bytes", content_type="application/octet-stream"
        )
        client.begin_analyze_binary.return_value.result.assert_called_once_with()
        client.close.assert_called_once_with()
        assert result.text == "Jane Doe\nJane"


class JsonResponse(HttpResponse):
    def __init__(
        self, request: HttpRequest, status: int, body: dict, headers: dict[str, str]
    ) -> None:
        super().__init__(request, None)
        self.status_code = status
        self.headers = CaseInsensitiveDict({"content-type": "application/json", **headers})
        self.content_type = "application/json"
        self._body = json.dumps(body).encode()

    def body(self) -> bytes:
        return self._body

    def read(self) -> bytes:
        return self._body

    def iter_bytes(self) -> Iterator[bytes]:
        yield self._body

    def json(self) -> dict:
        return json.loads(self._body)


def test_real_sdk_serializes_binary_codepoint_request_and_deserializes_poll_result() -> None:
    endpoint = "https://example.services.ai.azure.com"
    operation = f"{endpoint}/contentunderstanding/analyzerResults/test?api-version=2025-11-01"
    requests: list[HttpRequest] = []

    def send(request: HttpRequest, **kwargs: object) -> HttpResponse:
        requests.append(request)
        if request.method == "POST":
            return JsonResponse(
                request, 202, {"status": "Running"}, {"operation-location": operation}
            )
        assert request.method == "GET"
        assert request.url == operation
        return JsonResponse(
            request, 200, {"status": "Succeeded", "result": _result().as_dict()}, {}
        )

    transport = MagicMock(spec=HttpTransport)
    transport.send.side_effect = send
    credential = Mock(spec=TokenCredential)
    credential.get_token.return_value = AccessToken("synthetic-test-token", int(time.time()) + 3600)

    def client_factory(**kwargs: object) -> ContentUnderstandingClient:
        return ContentUnderstandingClient(**kwargs, transport=transport, polling_interval=0)

    with patch(
        "pii_redaction_demo.providers.azure_content_understanding.ContentUnderstandingClient",
        side_effect=client_factory,
    ):
        provider = AzureContentUnderstandingOcrProvider(endpoint, credential)
        result = provider.read_image(b"synthetic-image-bytes")
        provider.close()

    submitted = requests[0]
    url = urlsplit(submitted.url)
    assert url.path == "/contentunderstanding/analyzers/prebuilt-read:analyzeBinary"
    assert parse_qs(url.query) == {"api-version": ["2025-11-01"], "stringEncoding": ["codePoint"]}
    assert submitted.body == b"synthetic-image-bytes"
    assert submitted.headers["Content-Type"] == "application/octet-stream"
    assert len(requests) == 2
    assert result.text == "Jane Doe\nJane"
    assert result.regions[0].words[1].polygon == ((50, 0), (80, 0), (80, 10), (50, 10))


def test_defaults_to_entra_credential_and_propagates_poll_failure() -> None:
    with (
        patch(
            "pii_redaction_demo.providers.azure_content_understanding.ContentUnderstandingClient"
        ) as client_type,
        patch(
            "pii_redaction_demo.providers.azure_content_understanding.DefaultAzureCredential"
        ) as credential_type,
    ):
        client_type.return_value.begin_analyze_binary.return_value.result.side_effect = (
            HttpResponseError("OCR failed")
        )
        provider = AzureContentUnderstandingOcrProvider("https://example.test")
        with pytest.raises(HttpResponseError, match="OCR failed"):
            provider.read_image(b"image")
        assert client_type.call_args.kwargs["credential"] is credential_type.return_value


def test_blank_page_is_empty_but_missing_document_is_an_error() -> None:
    content = _content()
    content.pages[0].lines = []
    content.pages[0].words = []
    content.markdown = ""
    assert _to_ocr_result(_result(content)).text == ""
    with pytest.raises(ValueError, match="one document"):
        _to_ocr_result(AnalysisResult(contents=[]))
    with pytest.raises(ValueError, match="one document"):
        _to_ocr_result(AnalysisResult(contents=[content, content]))


def test_line_without_words_retains_line_polygon() -> None:
    content = _content()
    content.pages[0].words = None
    result = _to_ocr_result(_result(content))
    assert result.regions[0].words == ()
    assert result.regions[0].polygon == ((0, 0), (80, 0), (80, 10), (0, 10))


@pytest.mark.parametrize("unit", ["inch", None])
def test_rejects_non_pixel_coordinates(unit: str | None) -> None:
    content = _content()
    content.unit = unit
    with pytest.raises(ValueError, match="pixels"):
        _to_ocr_result(_result(content))


def test_rejects_multiple_or_missing_pages() -> None:
    content = _content()
    content.pages.append(content.pages[0])
    with pytest.raises(ValueError, match="single-page"):
        _to_ocr_result(_result(content))
    content.pages = []
    with pytest.raises(ValueError, match="single-page"):
        _to_ocr_result(_result(content))
    content = _content()
    content.end_page_number = 2
    with pytest.raises(ValueError, match="single-page"):
        _to_ocr_result(_result(content))


def test_rejects_text_without_lines_and_words_outside_lines() -> None:
    content = _content()
    content.pages[0].lines = []
    with pytest.raises(ValueError, match="no matching lines"):
        _to_ocr_result(_result(content))
    content.pages[0].words = []
    with pytest.raises(ValueError, match="no matching lines"):
        _to_ocr_result(_result(content))


def test_rejects_missing_spans_and_overlapping_lines() -> None:
    content = _content()
    content.pages[0].words[0].span = None
    with pytest.raises(ValueError, match="valid text spans"):
        _to_ocr_result(_result(content))
    content = _content()
    content.pages[0].lines.append(content.pages[0].lines[0])
    with pytest.raises(ValueError, match="multiple lines"):
        _to_ocr_result(_result(content))


@pytest.mark.parametrize(
    "source",
    [
        None,
        "",
        "D(2,0,0,10,10)",
        "D(1,0,0,10)",
        "D(1,nan,0,10,10)",
        "D(1,0,0,-1,10)",
        "D(1,0,0,10,10);D(1,20,20,10,10)",
        "D(1,bad,0,10,10)",
    ],
)
def test_rejects_invalid_missing_and_wrong_page_sources(source: str | None) -> None:
    with pytest.raises(ValueError):
        _to_polygon(source, 1)


def test_source_boxes_and_polygons_convert_to_pixel_pairs() -> None:
    assert _to_polygon("D(1,1.2,2.8,8.5,7.3)", 1) == ((1, 3), (10, 3), (10, 10), (1, 10))
    assert _to_polygon("D(1,0,0,20,2,18,12,-2,10)", 1) == (
        (0, 0),
        (20, 2),
        (18, 12),
        (-2, 10),
    )


class StubPiiProvider:
    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        assert list(documents) == ["\U0001f600 Jane Jane"]
        return [
            RedactionResult(
                original_text=documents[0],
                redacted_text="\U0001f600 Jane ****",
                entities=(PiiEntity("Jane", "Person", offset=7, length=4, confidence_score=1),),
            )
        ]


def test_unicode_and_repeated_words_mask_only_selected_pixels(tmp_path: Path) -> None:
    content = DocumentContent(
        start_page_number=1,
        end_page_number=1,
        unit="pixel",
        pages=[
            DocumentPage(
                page_number=1,
                lines=[
                    DocumentLine(
                        content="\U0001f600 Jane Jane",
                        span=ContentSpan(offset=0, length=11),
                        source="D(1,0,0,90,10)",
                    )
                ],
                words=[
                    DocumentWord(
                        content=text,
                        span=ContentSpan(offset=offset, length=len(text)),
                        source=f"D(1,{left},0,20,10)",
                    )
                    for text, offset, left in [
                        ("\U0001f600", 0, 0),
                        ("Jane", 2, 30),
                        ("Jane", 7, 60),
                    ]
                ],
            )
        ],
    )
    image_path = tmp_path / "synthetic.png"
    Image.new("RGB", (100, 30), "white").save(image_path)
    with patch(
        "pii_redaction_demo.providers.azure_content_understanding.ContentUnderstandingClient"
    ) as client_type:
        client_type.return_value.begin_analyze_binary.return_value.result.return_value = _result(
            content
        )
        pipeline = ImageRedactionPipeline(
            AzureContentUnderstandingOcrProvider("https://example.test", Mock()),
            PiiRedactionService(StubPiiProvider()),
            PillowImageRedactor(),
        )
        result = pipeline.process_image(image_path, tmp_path / "out")

    assert result.masked_polygons == 1
    assert result.redacted_text == "\U0001f600 Jane ****"
    with Image.open(io.BytesIO(result.output_path.read_bytes())) as masked:
        assert masked.getpixel((35, 5)) == (255, 255, 255)
        assert masked.getpixel((65, 5)) == (0, 0, 0)
