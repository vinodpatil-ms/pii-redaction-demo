import io

from PIL import Image

from pii_redaction_demo.providers.pillow_image import PillowImageRedactor


def _white_png(size: tuple[int, int] = (60, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_mask_paints_the_polygon_area_black() -> None:
    masked = PillowImageRedactor(padding=0).mask(
        _white_png(), [((10, 10), (30, 10), (30, 20), (10, 20))]
    )

    with Image.open(io.BytesIO(masked)) as image:
        assert image.format == "PNG"
        assert image.getpixel((20, 15)) == (0, 0, 0)
        assert image.getpixel((50, 35)) == (255, 255, 255)


def test_mask_clamps_boxes_to_the_image_bounds() -> None:
    masked = PillowImageRedactor(padding=50).mask(_white_png(), [((0, 0), (5, 0), (5, 5), (0, 5))])

    with Image.open(io.BytesIO(masked)) as image:
        assert image.getpixel((0, 0)) == (0, 0, 0)
        assert image.getpixel((55, 39)) == (0, 0, 0)


def test_mask_without_polygons_returns_an_unchanged_image() -> None:
    masked = PillowImageRedactor().mask(_white_png(), [])

    with Image.open(io.BytesIO(masked)) as image:
        assert image.getpixel((30, 20)) == (255, 255, 255)


def test_annotate_outlines_the_polygon_without_hiding_the_content() -> None:
    annotated = PillowImageRedactor(padding=0).annotate(
        _white_png(), [((10, 10), (30, 10), (30, 20), (10, 20))], outline="#ff0000"
    )

    with Image.open(io.BytesIO(annotated)) as image:
        assert image.getpixel((20, 10)) == (255, 0, 0)
        assert image.getpixel((20, 15)) == (255, 255, 255)


def test_annotate_blends_a_translucent_fill_over_the_content() -> None:
    annotated = PillowImageRedactor(padding=0).annotate(
        _white_png(),
        [((10, 10), (30, 10), (30, 20), (10, 20))],
        outline="#ff0000",
        fill=(255, 0, 0, 128),
    )

    with Image.open(io.BytesIO(annotated)) as image:
        red, green, blue = image.getpixel((20, 15))
        assert red == 255
        assert 100 < green < 200
        assert 100 < blue < 200
