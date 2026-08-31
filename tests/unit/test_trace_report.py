import io
import json
from pathlib import Path

from PIL import Image

from pii_redaction_demo.domain.models import OcrResult, PiiEntity, TextRegion
from pii_redaction_demo.providers.pillow_image import PillowImageRedactor
from pii_redaction_demo.services.pipeline import RedactedEmail, RedactedImage, WordSpan
from pii_redaction_demo.services.trace_report import write_trace

ENTITY = PiiEntity(
    text="Jane Doe",
    category="Person",
    offset=5,
    length=8,
    confidence_score=0.99,
    subcategory=None,
)


def _white_png(size: tuple[int, int] = (60, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def _image(tmp_path: Path) -> RedactedImage:
    source = tmp_path / "in" / "chat.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(_white_png())

    output = tmp_path / "out" / "chat.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_white_png())

    polygon = ((10, 10), (30, 10), (30, 20), (10, 20))
    return RedactedImage(
        source_path=source,
        output_path=output,
        text="Name Jane Doe",
        redacted_text="Name ********",
        entities=(ENTITY,),
        masked_polygons=1,
        ocr=OcrResult(text="Name Jane Doe", regions=(TextRegion(text="Name Jane Doe"),)),
        word_spans=(WordSpan(5, 13, polygon),),
        entity_polygons=(polygon,),
    )


def _email(tmp_path: Path) -> RedactedEmail:
    source = tmp_path / "in" / "note.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("Name Jane Doe")

    return RedactedEmail(
        source_path=source,
        output_path=tmp_path / "out" / "note.txt",
        text="Name Jane Doe",
        redacted_text="Name ********",
        entities=(ENTITY,),
    )


def test_write_trace_dumps_every_image_step(tmp_path: Path) -> None:
    report = write_trace(
        tmp_path / "trace",
        images=[_image(tmp_path)],
        annotator=PillowImageRedactor(),
        run_id="run-1",
    )

    steps = report.parent / "images" / "chat"
    assert sorted(path.name for path in steps.iterdir()) == [
        "01-source.png",
        "02-ocr.json",
        "02-ocr.png",
        "03-document.json",
        "03-document.txt",
        "04-pii.json",
        "04-pii.png",
        "05-redacted.png",
    ]

    entities = json.loads((steps / "04-pii.json").read_text())["entities"]
    assert entities[0]["category"] == "Person"
    assert (steps / "03-document.txt").read_text() == "Name Jane Doe"


def test_write_trace_skips_annotations_without_an_annotator(tmp_path: Path) -> None:
    report = write_trace(tmp_path / "trace", images=[_image(tmp_path)], run_id="run-1")

    steps = report.parent / "images" / "chat"
    assert not (steps / "02-ocr.png").exists()
    assert (steps / "02-ocr.json").exists()


def test_write_trace_dumps_email_steps_and_highlights_entities(tmp_path: Path) -> None:
    report = write_trace(tmp_path / "trace", emails=[_email(tmp_path)], run_id="run-1")

    steps = report.parent / "emails" / "note"
    assert (steps / "01-source.txt").read_text() == "Name Jane Doe"
    assert (steps / "03-redacted.txt").read_text() == "Name ********"

    page = report.read_text(encoding="utf-8")
    assert '<mark title="Person">Jane Doe</mark>' in page
    assert "Name ********" in page


def test_write_trace_reports_when_nothing_was_processed(tmp_path: Path) -> None:
    report = write_trace(tmp_path / "trace", run_id="run-1")

    assert "Nothing was processed." in report.read_text(encoding="utf-8")
