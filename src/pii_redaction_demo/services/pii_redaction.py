from collections.abc import Sequence

from pii_redaction_demo.domain.models import PiiEntity, RedactionResult
from pii_redaction_demo.providers.protocols import PiiRedactionProvider

# Azure AI Language caps a PII request at 5 documents.
MAX_DOCUMENTS_PER_REQUEST = 5
MASK_CHARACTER = "*"


class PiiRedactionService:
    """Masks PII in text, batching requests within the Azure AI Language limits."""

    def __init__(
        self,
        provider: PiiRedactionProvider,
        *,
        language: str = "en",
        categories: Sequence[str] | None = None,
        min_confidence: float = 0.0,
    ) -> None:
        self._provider = provider
        self._language = language
        self._categories = tuple(categories) if categories else None
        self._min_confidence = min_confidence

    def redact_text(self, text: str) -> RedactionResult:
        return self.redact_batch([text])[0]

    def redact_batch(self, documents: Sequence[str]) -> list[RedactionResult]:
        if not documents:
            return []

        results: list[RedactionResult] = []
        for start in range(0, len(documents), MAX_DOCUMENTS_PER_REQUEST):
            batch = documents[start : start + MAX_DOCUMENTS_PER_REQUEST]
            results.extend(
                self._apply_threshold(result)
                for result in self._provider.redact(
                    batch,
                    language=self._language,
                    categories=self._categories,
                )
            )
        return results

    def _apply_threshold(self, result: RedactionResult) -> RedactionResult:
        """Drops low-confidence detections and re-masks so the text matches the kept entities."""
        if self._min_confidence <= 0.0:
            return result

        kept = tuple(
            entity for entity in result.entities if entity.confidence_score >= self._min_confidence
        )
        if len(kept) == len(result.entities):
            return result

        return RedactionResult(
            original_text=result.original_text,
            redacted_text=_mask(result.original_text, kept),
            entities=kept,
        )


def _mask(text: str, entities: Sequence[PiiEntity]) -> str:
    parts: list[str] = []
    cursor = 0
    for entity in sorted(entities, key=lambda item: item.offset):
        end = entity.offset + entity.length
        if end <= cursor:
            continue
        start = max(cursor, entity.offset)
        parts.append(text[cursor:start])
        parts.append(MASK_CHARACTER * (end - start))
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)
