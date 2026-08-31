from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class TextRegion:
    """A line of recognized text, its polygon in image pixel coordinates, and its words."""

    text: str
    polygon: tuple[tuple[int, int], ...] = ()
    words: tuple["TextRegion", ...] = ()


@dataclass(frozen=True, slots=True)
class OcrResult:
    text: str
    regions: tuple[TextRegion, ...] = ()
    model_version: str | None = None


@dataclass(frozen=True, slots=True)
class PiiEntity:
    text: str
    category: str
    offset: int
    length: int
    confidence_score: float
    subcategory: str | None = None


@dataclass(frozen=True, slots=True)
class RedactionResult:
    original_text: str
    redacted_text: str
    entities: tuple[PiiEntity, ...] = field(default_factory=tuple)
