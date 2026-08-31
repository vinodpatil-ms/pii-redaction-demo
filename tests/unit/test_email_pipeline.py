from collections.abc import Sequence
from pathlib import Path

import pytest

from pii_redaction_demo.domain.models import PiiEntity, RedactionResult
from pii_redaction_demo.services.pii_redaction import PiiRedactionService
from pii_redaction_demo.services.pipeline import EmailRedactionPipeline

PERSON = PiiEntity(text="Jane Doe", category="Person", offset=6, length=8, confidence_score=0.99)


class StubPiiProvider:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        self.batches.append(list(documents))
        return [
            RedactionResult(
                original_text=document,
                redacted_text=document.replace("Jane Doe", "*" * 8),
                entities=(PERSON,),
            )
            for document in documents
        ]


def _build() -> tuple[EmailRedactionPipeline, StubPiiProvider]:
    provider = StubPiiProvider()
    return EmailRedactionPipeline(PiiRedactionService(provider)), provider


def test_pipeline_writes_redacted_copies_under_the_same_file_name(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    (source / "email_01.txt").write_text("From: Jane Doe\n", encoding="utf-8")
    (source / "notes.pdf").write_bytes(b"ignored")
    pipeline, _ = _build()

    results = pipeline.run(source, tmp_path / "out")

    assert [result.source_path.name for result in results] == ["email_01.txt"]
    assert results[0].output_path == tmp_path / "out" / "email_01.txt"
    assert results[0].output_path.read_text(encoding="utf-8") == "From: ********\n"
    assert results[0].entities == (PERSON,)


def test_pipeline_batches_documents_within_the_language_limit(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    for index in range(6):
        (source / f"email_{index}.txt").write_text(f"Hi Jane Doe {index}", encoding="utf-8")
    pipeline, provider = _build()

    results = pipeline.run(source, tmp_path / "out")

    assert len(results) == 6
    assert [len(batch) for batch in provider.batches] == [5, 1]


def test_pipeline_rejects_a_missing_input_directory(tmp_path: Path) -> None:
    pipeline, _ = _build()

    with pytest.raises(NotADirectoryError):
        pipeline.run(tmp_path / "missing", tmp_path / "out")


def test_pipeline_skips_the_provider_when_there_is_nothing_to_redact(tmp_path: Path) -> None:
    source = tmp_path / "in"
    source.mkdir()
    pipeline, provider = _build()

    assert pipeline.run(source, tmp_path / "out") == []
    assert provider.batches == []
