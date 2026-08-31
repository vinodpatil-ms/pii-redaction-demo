from collections.abc import Sequence

from pii_redaction_demo.domain.models import PiiEntity, RedactionResult
from pii_redaction_demo.services.pii_redaction import (
    MAX_DOCUMENTS_PER_REQUEST,
    PiiRedactionService,
)


class FakePiiProvider:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.languages: list[str] = []
        self.categories: list[Sequence[str] | None] = []

    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        self.batches.append(list(documents))
        self.languages.append(language)
        self.categories.append(categories)
        return [
            RedactionResult(original_text=document, redacted_text="*" * len(document))
            for document in documents
        ]


class ScoredPiiProvider:
    """Returns 'Jane' at 0.95 and 'Doe' at 0.40 for the text 'Hi Jane Doe'."""

    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        return [
            RedactionResult(
                original_text=document,
                redacted_text="Hi **** ***",
                entities=(
                    PiiEntity(
                        text="Jane",
                        category="Person",
                        offset=3,
                        length=4,
                        confidence_score=0.95,
                    ),
                    PiiEntity(
                        text="Doe",
                        category="Person",
                        offset=8,
                        length=3,
                        confidence_score=0.40,
                    ),
                ),
            )
            for document in documents
        ]


def test_redact_text_returns_single_result() -> None:
    provider = FakePiiProvider()

    result = PiiRedactionService(provider).redact_text("ssn 111")

    assert result.redacted_text == "*******"
    assert provider.batches == [["ssn 111"]]


def test_redact_batch_splits_requests_at_the_service_limit() -> None:
    provider = FakePiiProvider()
    documents = [f"doc {index}" for index in range(MAX_DOCUMENTS_PER_REQUEST + 2)]

    results = PiiRedactionService(provider).redact_batch(documents)

    assert len(results) == len(documents)
    assert [len(batch) for batch in provider.batches] == [MAX_DOCUMENTS_PER_REQUEST, 2]


def test_language_and_categories_are_forwarded() -> None:
    provider = FakePiiProvider()

    PiiRedactionService(provider, language="fr", categories=["USSocialSecurityNumber"]).redact_text(
        "abc"
    )

    assert provider.languages == ["fr"]
    assert provider.categories == [("USSocialSecurityNumber",)]


def test_empty_batch_skips_the_provider() -> None:
    provider = FakePiiProvider()

    assert PiiRedactionService(provider).redact_batch([]) == []
    assert provider.batches == []


def test_every_detection_is_kept_when_no_threshold_is_set() -> None:
    result = PiiRedactionService(ScoredPiiProvider()).redact_text("Hi Jane Doe")

    assert len(result.entities) == 2
    assert result.redacted_text == "Hi **** ***"


def test_detections_below_the_threshold_are_dropped_and_the_text_is_re_masked() -> None:
    service = PiiRedactionService(ScoredPiiProvider(), min_confidence=0.8)

    result = service.redact_text("Hi Jane Doe")

    assert [entity.text for entity in result.entities] == ["Jane"]
    assert result.redacted_text == "Hi **** Doe"
