from collections.abc import Sequence
from pathlib import Path

import pytest

from pii_redaction_demo.domain.models import OcrResult, PiiEntity, RedactionResult, TextRegion
from pii_redaction_demo.providers.protocols import Polygon
from pii_redaction_demo.services.pii_redaction import PiiRedactionService
from pii_redaction_demo.services.pipeline import ImageRedactionPipeline


def _word(text: str, x: int) -> TextRegion:
    return TextRegion(text=text, polygon=((x, 0), (x + 10, 0), (x + 10, 10), (x, 10)))


OCR_RESULT = OcrResult(
    text="Name Jane Doe\ncall me",
    regions=(
        TextRegion(
            text="Name Jane Doe",
            polygon=((0, 0), (60, 0), (60, 10), (0, 10)),
            words=(_word("Name", 0), _word("Jane", 20), _word("Doe", 40)),
        ),
        TextRegion(
            text="call me",
            polygon=((0, 20), (30, 20), (30, 30), (0, 30)),
            words=(_word("call", 0), _word("me", 20)),
        ),
    ),
)


class StubOcrProvider:
    def read_image(self, image: bytes) -> OcrResult:
        return OCR_RESULT


class StubPiiProvider:
    def __init__(self, entities: tuple[PiiEntity, ...]) -> None:
        self._entities = entities
        self.documents: list[str] = []

    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        self.documents.extend(documents)
        return [
            RedactionResult(
                original_text=document,
                redacted_text=document.replace("Jane Doe", "*" * 8),
                entities=self._entities,
            )
            for document in documents
        ]


class SpyImageRedactor:
    def __init__(self) -> None:
        self.polygons: list[Polygon] = []

    def mask(self, image: bytes, polygons: Sequence[Polygon]) -> bytes:
        self.polygons = list(polygons)
        return b"masked:" + image


def _build(entities: tuple[PiiEntity, ...]) -> tuple[ImageRedactionPipeline, SpyImageRedactor]:
    redactor = SpyImageRedactor()
    pipeline = ImageRedactionPipeline(
        ocr=StubOcrProvider(),
        redaction=PiiRedactionService(StubPiiProvider(entities)),
        image_redactor=redactor,
    )
    return pipeline, redactor


def _person_entity() -> PiiEntity:
    return PiiEntity(
        text="Jane Doe",
        category="Person",
        offset=5,
        length=8,
        confidence_score=0.99,
    )


def test_pipeline_masks_only_words_covered_by_the_entity(tmp_path: Path) -> None:
    pipeline, redactor = _build((_person_entity(),))
    image_path = tmp_path / "chat.png"
    image_path.write_bytes(b"raw-image")

    result = pipeline.process_image(image_path, tmp_path / "out")

    assert redactor.polygons == [_word("Jane", 20).polygon, _word("Doe", 40).polygon]
    assert result.masked_polygons == 2
    assert result.redacted_text == "Name ********\ncall me"
    assert result.output_path.read_bytes() == b"masked:raw-image"


def test_entity_offsets_account_for_the_line_separator(tmp_path: Path) -> None:
    entity = PiiEntity(
        text="call",
        category="Person",
        offset=14,
        length=4,
        confidence_score=0.5,
    )
    pipeline, redactor = _build((entity,))
    image_path = tmp_path / "chat.png"
    image_path.write_bytes(b"raw-image")

    pipeline.process_image(image_path, tmp_path / "out")

    assert redactor.polygons == [_word("call", 0).polygon]


def test_run_processes_supported_images_and_skips_other_files(tmp_path: Path) -> None:
    pipeline, _ = _build((_person_entity(),))
    input_dir = tmp_path / "input-images"
    input_dir.mkdir()
    (input_dir / "a.jpg").write_bytes(b"a")
    (input_dir / "b.png").write_bytes(b"b")
    (input_dir / "notes.txt").write_text("ignore me")

    results = pipeline.run(input_dir, tmp_path / "output-images")

    assert [result.source_path.name for result in results] == ["a.jpg", "b.png"]
    assert all(result.output_path.exists() for result in results)


def test_run_rejects_a_missing_input_directory(tmp_path: Path) -> None:
    pipeline, _ = _build(())

    with pytest.raises(NotADirectoryError):
        pipeline.run(tmp_path / "missing", tmp_path / "out")
