import io
from collections.abc import Sequence

from PIL import Image, ImageDraw

from pii_redaction_demo.providers.protocols import Polygon, Rgba


class PillowImageRedactor:
    """Paints opaque boxes over the supplied polygons using Pillow."""

    def __init__(self, fill: str = "black", padding: int = 2, outline_width: int = 2) -> None:
        self._fill = fill
        self._padding = padding
        self._outline_width = outline_width

    def mask(self, image: bytes, polygons: Sequence[Polygon]) -> bytes:
        with Image.open(io.BytesIO(image)) as source:
            image_format = source.format or "PNG"
            canvas = source.convert("RGB")

        draw = ImageDraw.Draw(canvas)
        for polygon in polygons:
            box = _bounding_box(polygon, self._padding, canvas.size)
            if box is not None:
                draw.rectangle(box, fill=self._fill)

        buffer = io.BytesIO()
        canvas.save(buffer, format=image_format)
        return buffer.getvalue()

    def annotate(
        self,
        image: bytes,
        polygons: Sequence[Polygon],
        *,
        outline: str,
        fill: Rgba | None = None,
    ) -> bytes:
        with Image.open(io.BytesIO(image)) as source:
            image_format = source.format or "PNG"
            canvas = source.convert("RGBA")

        # Drawn on a separate layer so a translucent fill blends with the pixels underneath.
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        for polygon in polygons:
            box = _bounding_box(polygon, self._padding, canvas.size)
            if box is not None:
                draw.rectangle(box, outline=outline, fill=fill, width=self._outline_width)

        merged = Image.alpha_composite(canvas, overlay).convert("RGB")
        buffer = io.BytesIO()
        merged.save(buffer, format=image_format)
        return buffer.getvalue()


def _bounding_box(
    polygon: Polygon,
    padding: int,
    size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    if not polygon:
        return None

    width, height = size
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    left = max(0, min(xs) - padding)
    top = max(0, min(ys) - padding)
    right = min(width - 1, max(xs) + padding)
    bottom = min(height - 1, max(ys) + padding)
    if right < left or bottom < top:
        return None
    return left, top, right, bottom
