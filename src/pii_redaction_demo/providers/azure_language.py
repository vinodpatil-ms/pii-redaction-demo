from collections.abc import Sequence

from azure.ai.textanalytics import RecognizePiiEntitiesResult, TextAnalyticsClient
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from pii_redaction_demo.domain.models import PiiEntity, RedactionResult


class AzureLanguagePiiProvider:
    """Detects and masks PII with the Azure AI Language PII recognition API."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential | None = None,
    ) -> None:
        # The accounts deployed by infra/terraform have local auth disabled, so Entra ID
        # tokens are the only supported data-plane credential.
        self._client = TextAnalyticsClient(
            endpoint=endpoint,
            credential=credential or DefaultAzureCredential(),
        )

    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]:
        responses = self._client.recognize_pii_entities(
            list(documents),
            language=language,
            categories_filter=list(categories) if categories else None,
        )

        results: list[RedactionResult] = []
        for original, response in zip(documents, responses, strict=True):
            if response.is_error:
                raise RuntimeError(
                    "Azure AI Language PII recognition failed: "
                    f"{response.error.code}: {response.error.message}"
                )
            results.append(_to_redaction_result(original, response))
        return results

    def close(self) -> None:
        self._client.close()


def _to_redaction_result(original: str, response: RecognizePiiEntitiesResult) -> RedactionResult:
    return RedactionResult(
        original_text=original,
        redacted_text=response.redacted_text,
        entities=tuple(
            PiiEntity(
                text=entity.text,
                category=str(entity.category),
                subcategory=entity.subcategory,
                offset=entity.offset,
                length=entity.length,
                confidence_score=entity.confidence_score,
            )
            for entity in response.entities
        ),
    )
