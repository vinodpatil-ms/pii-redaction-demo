"""Ports the services depend on. Adapters in this package implement them."""

from collections.abc import Sequence
from typing import Protocol

from pii_redaction_demo.domain.models import OcrResult, RedactionResult

Polygon = Sequence[tuple[int, int]]
Rgba = tuple[int, int, int, int]


class OcrProvider(Protocol):
    def read_image(self, image: bytes) -> OcrResult: ...


class PiiRedactionProvider(Protocol):
    def redact(
        self,
        documents: Sequence[str],
        *,
        language: str,
        categories: Sequence[str] | None = None,
    ) -> list[RedactionResult]: ...


class ImageRedactor(Protocol):
    def mask(self, image: bytes, polygons: Sequence[Polygon]) -> bytes: ...


class ImageAnnotator(Protocol):
    """Draws non-destructive boxes so a reviewer can see what each step selected."""

    def annotate(
        self,
        image: bytes,
        polygons: Sequence[Polygon],
        *,
        outline: str,
        fill: Rgba | None = None,
    ) -> bytes: ...
