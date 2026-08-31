"""Directory pipelines: images go through OCR first, emails go straight to PII detection."""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pii_redaction_demo.domain.models import OcrResult, PiiEntity, RedactionResult, TextRegion
from pii_redaction_demo.providers.protocols import ImageRedactor, OcrProvider, Polygon
from pii_redaction_demo.services.pii_redaction import PiiRedactionService

IMAGE_SUFFIXES = frozenset({".bmp", ".jpeg", ".jpg", ".png", ".tiff"})
EMAIL_SUFFIXES = frozenset({".eml", ".txt"})
LINE_SEPARATOR = "\n"
ENCODING = "utf-8"

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WordSpan:
    """Where a recognized word landed in the flattened document, and its image polygon."""

    start: int
    end: int
    polygon: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class RedactedImage:
    source_path: Path
    output_path: Path
    text: str
    redacted_text: str
    entities: tuple[PiiEntity, ...]
    masked_polygons: int
    ocr: OcrResult | None = None
    word_spans: tuple[WordSpan, ...] = ()
    entity_polygons: tuple[Polygon, ...] = ()


@dataclass(frozen=True, slots=True)
class RedactedEmail:
    source_path: Path
    output_path: Path
    text: str
    redacted_text: str
    entities: tuple[PiiEntity, ...]


class ImageRedactionPipeline:
    """Runs OCR, detects PII in the recognized text, and masks the matching image areas."""

    def __init__(
        self,
        ocr: OcrProvider,
        redaction: PiiRedactionService,
        image_redactor: ImageRedactor,
    ) -> None:
        self._ocr = ocr
        self._redaction = redaction
        self._image_redactor = image_redactor

    def run(self, input_dir: str | Path, output_dir: str | Path) -> list[RedactedImage]:
        paths = _iter_files(input_dir, IMAGE_SUFFIXES)
        if not paths:
            logger.info("no images to redact in %s", input_dir)
            return []

        destination = _prepare(output_dir)
        logger.info("redacting %d image(s) from %s", len(paths), input_dir)
        return [self.process_image(path, destination) for path in paths]

    def process_image(self, image_path: str | Path, output_dir: str | Path) -> RedactedImage:
        source = Path(image_path)
        image = source.read_bytes()

        # Core pipeline: OCR -> PII detection -> image masking
        ocr_result = self._ocr.read_image(image)
        document, spans = _flatten(ocr_result)
        redaction = self._redaction.redact_text(document)
        polygons = _polygons_for_entities(redaction.entities, spans)

        output_path = Path(output_dir) / source.name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(self._image_redactor.mask(image, polygons))

        logger.info(
            "%s: %d word(s) read, %d entity(ies), %d box(es) -> %s",
            source.name,
            len(spans),
            len(redaction.entities),
            len(polygons),
            output_path,
        )
        return RedactedImage(
            source_path=source,
            output_path=output_path,
            text=document,
            redacted_text=redaction.redacted_text,
            entities=redaction.entities,
            masked_polygons=len(polygons),
            ocr=ocr_result,
            word_spans=tuple(spans),
            entity_polygons=tuple(polygons),
        )


class EmailRedactionPipeline:
    """Masks PII in plain-text emails, writing each result under the same file name."""

    def __init__(self, redaction: PiiRedactionService) -> None:
        self._redaction = redaction

    def run(self, input_dir: str | Path, output_dir: str | Path) -> list[RedactedEmail]:
        paths = _iter_files(input_dir, EMAIL_SUFFIXES)
        if not paths:
            logger.info("no emails to redact in %s", input_dir)
            return []

        destination = _prepare(output_dir)
        logger.info("redacting %d email(s) from %s", len(paths), input_dir)

        documents = [path.read_text(encoding=ENCODING) for path in paths]
        results = self._redaction.redact_batch(documents)
        return [
            _write_email(path, destination, result)
            for path, result in zip(paths, results, strict=True)
        ]


def _iter_files(directory: str | Path, suffixes: frozenset[str]) -> list[Path]:
    source = Path(directory)
    if not source.is_dir():
        raise NotADirectoryError(f"input directory not found: {source}")

    return sorted(
        path for path in source.iterdir() if path.is_file() and path.suffix.lower() in suffixes
    )


def _prepare(output_dir: str | Path) -> Path:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _write_email(source: Path, destination: Path, result: RedactionResult) -> RedactedEmail:
    output_path = destination / source.name
    output_path.write_text(result.redacted_text, encoding=ENCODING)

    logger.info("%s: %d entity(ies) -> %s", source.name, len(result.entities), output_path)
    return RedactedEmail(
        source_path=source,
        output_path=output_path,
        text=result.original_text,
        redacted_text=result.redacted_text,
        entities=result.entities,
    )


def _flatten(ocr_result: OcrResult) -> tuple[str, list[WordSpan]]:
    """Rebuilds the OCR document and records where each word sits in it."""
    parts: list[str] = []
    spans: list[WordSpan] = []
    cursor = 0

    for region in ocr_result.regions:
        parts.append(region.text)
        spans.extend(_region_spans(region, cursor))
        cursor += len(region.text) + len(LINE_SEPARATOR)

    return LINE_SEPARATOR.join(parts), spans


def _region_spans(region: TextRegion, offset: int) -> list[WordSpan]:
    if not region.words:
        return [WordSpan(offset, offset + len(region.text), region.polygon)]

    spans: list[WordSpan] = []
    cursor = 0
    for word in region.words:
        found = region.text.find(word.text, cursor)
        start = found if found >= 0 else cursor
        spans.append(WordSpan(offset + start, offset + start + len(word.text), word.polygon))
        cursor = start + len(word.text)
    return spans


def _polygons_for_entities(
    entities: Iterable[PiiEntity],
    spans: Sequence[WordSpan],
) -> list[Polygon]:
    polygons: list[Polygon] = []
    for entity in entities:
        entity_end = entity.offset + entity.length
        polygons.extend(
            span.polygon
            for span in spans
            if span.polygon and span.start < entity_end and entity.offset < span.end
        )
    return polygons
