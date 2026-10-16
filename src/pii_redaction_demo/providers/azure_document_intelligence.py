import io
from collections.abc import Sequence

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from pii_redaction_demo.domain.models import OcrResult, TextRegion


class AzureDocumentIntelligenceOcrProvider:
    """Reads image text with the GA Document Intelligence prebuilt-read model."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential | None = None,
    ) -> None:
        self._client = DocumentIntelligenceClient(
            endpoint=endpoint,
            credential=credential or DefaultAzureCredential(),
            api_version="2024-11-30",
        )

    def read_image(self, image: bytes) -> OcrResult:
        poller = self._client.begin_analyze_document(
            "prebuilt-read",
            body=io.BytesIO(image),
            content_type="application/octet-stream",
            string_index_type="unicodeCodePoint",
        )
        return _to_ocr_result(poller.result())

    def close(self) -> None:
        self._client.close()


def _to_ocr_result(result: AnalyzeResult) -> OcrResult:
    if len(result.pages) > 1:
        raise ValueError("Image redaction supports only single-page images.")

    regions: list[TextRegion] = []
    for page in result.pages:
        if page.unit != "pixel":
            raise ValueError("Image redaction requires OCR coordinates in pixels.")
        for line in page.lines or []:
            words = tuple(
                TextRegion(text=word.content, polygon=_to_polygon(word.polygon))
                for word in sorted(page.words or [], key=lambda word: word.span.offset)
                if any(
                    word.span.offset >= span.offset
                    and word.span.offset + word.span.length <= span.offset + span.length
                    for span in line.spans
                )
            )
            regions.append(
                TextRegion(text=line.content, polygon=_to_polygon(line.polygon), words=words)
            )
    return OcrResult(text="\n".join(region.text for region in regions), regions=tuple(regions))


def _to_polygon(coordinates: Sequence[float] | None) -> tuple[tuple[int, int], ...]:
    if not coordinates:
        return ()
    return tuple(
        (round(horizontal), round(vertical))
        for horizontal, vertical in zip(coordinates[::2], coordinates[1::2], strict=True)
    )
