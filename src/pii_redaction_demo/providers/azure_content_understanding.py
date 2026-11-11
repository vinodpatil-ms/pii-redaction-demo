import math
import re

from azure.ai.contentunderstanding import ContentUnderstandingClient
from azure.ai.contentunderstanding.models import (
    AnalysisResult,
    ContentSpan,
    DocumentContent,
    DocumentLine,
    DocumentWord,
)
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from pii_redaction_demo.domain.models import OcrResult, TextRegion


class AzureContentUnderstandingOcrProvider:
    """Reads image text with the GA Content Understanding prebuilt-read analyzer."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential | None = None,
    ) -> None:
        self._client = ContentUnderstandingClient(
            endpoint=endpoint,
            credential=credential or DefaultAzureCredential(),
            api_version="2025-11-01",
        )

    def read_image(self, image: bytes) -> OcrResult:
        # The Python SDK requests codePoint spans, matching Python string indexing.
        poller = self._client.begin_analyze_binary(
            "prebuilt-read",
            image,
            content_type="application/octet-stream",
        )
        return _to_ocr_result(poller.result())

    def close(self) -> None:
        self._client.close()


def _to_ocr_result(result: AnalysisResult) -> OcrResult:
    if len(result.contents) != 1 or not isinstance(result.contents[0], DocumentContent):
        raise ValueError("Image redaction requires one document content result.")
    content = result.contents[0]
    if (
        content.start_page_number != content.end_page_number
        or not content.pages
        or len(content.pages) != 1
    ):
        raise ValueError("Image redaction supports only single-page images.")
    if content.unit != "pixel":
        raise ValueError("Image redaction requires OCR coordinates in pixels.")

    page = content.pages[0]
    words = sorted(page.words or [], key=lambda word: _span(word).offset)
    remaining = set(range(len(words)))
    regions: list[TextRegion] = []
    for line in sorted(page.lines or [], key=lambda line: _span(line).offset):
        line_span = _span(line)
        line_words: list[TextRegion] = []
        for index, word in enumerate(words):
            word_span = _span(word)
            if (
                word_span.offset >= line_span.offset
                and word_span.offset + word_span.length <= line_span.offset + line_span.length
            ):
                if index not in remaining:
                    raise ValueError("OCR word belongs to multiple lines.")
                remaining.remove(index)
                line_words.append(
                    TextRegion(
                        text=word.content,
                        polygon=_to_polygon(word.source, page.page_number),
                    )
                )
        regions.append(
            TextRegion(
                text=line.content,
                polygon=_to_polygon(line.source, page.page_number),
                words=tuple(line_words),
            )
        )
    if remaining or (not regions and content.markdown and content.markdown.strip()):
        raise ValueError("OCR text has no matching lines; refusing to leave it unmasked.")
    return OcrResult(text="\n".join(region.text for region in regions), regions=tuple(regions))


def _span(element: DocumentLine | DocumentWord) -> ContentSpan:
    span = element.span
    if span is None or span.offset < 0 or span.length <= 0:
        raise ValueError("OCR lines and words require valid text spans.")
    return span


def _to_polygon(source: str | None, page_number: int) -> tuple[tuple[int, int], ...]:
    # CU encodes source locations as D(page,x1,y1,...), or D(page,left,top,width,height).
    match = re.fullmatch(r"D\((\d+),([^)]+)\)", source or "")
    if match is None or int(match[1]) != page_number:
        raise ValueError("OCR source must identify a bounding region on the image page.")
    coordinates = [float(value) for value in match[2].split(",")]
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError("OCR source coordinates must be finite.")
    if len(coordinates) == 4:
        left, top, width, height = coordinates
        if width <= 0 or height <= 0:
            raise ValueError("OCR source bounding box must have positive dimensions.")
        coordinates = [
            left,
            top,
            left + width,
            top,
            left + width,
            top + height,
            left,
            top + height,
        ]
    if len(coordinates) != 8:
        raise ValueError("OCR source must contain a box or a four-point polygon.")
    return tuple(
        (round(x), round(y)) for x, y in zip(coordinates[::2], coordinates[1::2], strict=True)
    )
