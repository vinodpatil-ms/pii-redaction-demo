"""Writes the raw output of every pipeline step plus a side-by-side HTML review page."""

import html
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from pii_redaction_demo.domain.models import PiiEntity
from pii_redaction_demo.providers.protocols import ImageAnnotator, Rgba
from pii_redaction_demo.services.pipeline import RedactedEmail, RedactedImage

ENCODING = "utf-8"
RUN_ID_FORMAT = "%Y%m%d-%H%M%S"
OCR_OUTLINE = "#22c55e"
PII_OUTLINE = "#ef4444"
PII_FILL: Rgba = (239, 68, 68, 80)


def write_trace(
    root: str | Path,
    *,
    images: Sequence[RedactedImage] = (),
    emails: Sequence[RedactedEmail] = (),
    annotator: ImageAnnotator | None = None,
    run_id: str | None = None,
) -> Path:
    """Dumps per-step artifacts under `root/<run_id>/` and returns the report path."""
    run = Path(root) / (run_id or datetime.now().strftime(RUN_ID_FORMAT))
    run.mkdir(parents=True, exist_ok=True)

    sections = [_image_section(image, run, annotator) for image in images]
    sections += [_email_section(email, run) for email in emails]

    report = run / "report.html"
    report.write_text(_page(run.name, len(images), len(emails), sections), encoding=ENCODING)
    return report


def _image_section(image: RedactedImage, run: Path, annotator: ImageAnnotator | None) -> str:
    stem = image.source_path.stem
    steps = run / "images" / stem
    steps.mkdir(parents=True, exist_ok=True)

    original = image.source_path.read_bytes()
    suffix = image.source_path.suffix or ".png"
    word_polygons = tuple(span.polygon for span in image.word_spans if span.polygon)
    panels: list[tuple[str, str]] = []

    (steps / f"01-source{suffix}").write_bytes(original)
    panels.append((f"01-source{suffix}", "1 &middot; Source"))

    ocr_payload = asdict(image.ocr) if image.ocr is not None else {}
    _write_json(steps / "02-ocr.json", ocr_payload)
    if annotator is not None:
        name = f"02-ocr{suffix}"
        annotated = annotator.annotate(original, word_polygons, outline=OCR_OUTLINE)
        (steps / name).write_bytes(annotated)
        panels.append((name, f"2 &middot; OCR &mdash; {len(word_polygons)} words"))

    (steps / "03-document.txt").write_text(image.text, encoding=ENCODING)
    _write_json(
        steps / "03-document.json",
        {"spans": [asdict(span) for span in image.word_spans]},
    )

    _write_json(
        steps / "04-pii.json",
        {
            "entities": [asdict(entity) for entity in image.entities],
            "redacted_text": image.redacted_text,
            "polygons": [list(polygon) for polygon in image.entity_polygons],
        },
    )
    if annotator is not None:
        name = f"04-pii{suffix}"
        matched = annotator.annotate(
            original, image.entity_polygons, outline=PII_OUTLINE, fill=PII_FILL
        )
        (steps / name).write_bytes(matched)
        panels.append((name, f"4 &middot; PII match &mdash; {len(image.entities)} entities"))

    name = f"05-redacted{suffix}"
    (steps / name).write_bytes(image.output_path.read_bytes())
    panels.append((name, f"5 &middot; Redacted &mdash; {image.masked_polygons} boxes"))

    base = f"images/{stem}"
    return "\n".join(
        [
            f"<section><h2>{html.escape(image.source_path.name)} "
            '<span class="kind">image</span></h2>',
            _strip(base, panels),
            _entity_table(image.entities),
            _details(
                "2 &middot; OCR &mdash; raw",
                _pretty(ocr_payload),
                f"{base}/02-ocr.json",
            ),
            _details(
                "3 &middot; Flattened document &mdash; raw",
                image.text,
                f"{base}/03-document.txt",
            ),
            _details(
                "4 &middot; PII entities &mdash; raw",
                _pretty({"entities": [asdict(e) for e in image.entities]}),
                f"{base}/04-pii.json",
            ),
            "</section>",
        ]
    )


def _email_section(email: RedactedEmail, run: Path) -> str:
    stem = email.source_path.stem
    steps = run / "emails" / stem
    steps.mkdir(parents=True, exist_ok=True)

    (steps / "01-source.txt").write_text(email.text, encoding=ENCODING)
    payload = {
        "entities": [asdict(entity) for entity in email.entities],
        "redacted_text": email.redacted_text,
    }
    _write_json(steps / "02-pii.json", payload)
    (steps / "03-redacted.txt").write_text(email.redacted_text, encoding=ENCODING)

    base = f"emails/{stem}"
    return "\n".join(
        [
            f"<section><h2>{html.escape(email.source_path.name)} "
            '<span class="kind">email</span></h2>',
            '<div class="cols">',
            f"<figure><figcaption>1 &middot; Source &mdash; {len(email.entities)} entities"
            f'</figcaption><pre class="text">{_highlight(email.text, email.entities)}</pre>'
            "</figure>",
            "<figure><figcaption>3 &middot; Redacted</figcaption>"
            f'<pre class="text">{html.escape(email.redacted_text)}</pre></figure>',
            "</div>",
            _entity_table(email.entities),
            _details(
                "2 &middot; PII entities &mdash; raw",
                _pretty(payload),
                f"{base}/02-pii.json",
            ),
            "</section>",
        ]
    )


def _strip(base: str, panels: Sequence[tuple[str, str]]) -> str:
    figures = "".join(
        f'<figure><a href="{base}/{name}"><img src="{base}/{name}" alt="{caption}"></a>'
        f"<figcaption>{caption}</figcaption></figure>"
        for name, caption in panels
    )
    return f'<div class="strip">{figures}</div>'


def _entity_table(entities: Sequence[PiiEntity]) -> str:
    if not entities:
        return '<p class="empty">No PII detected.</p>'

    rows = "".join(
        "<tr>"
        f"<td>{html.escape(entity.category)}</td>"
        f"<td>{html.escape(entity.subcategory or '—')}</td>"
        f"<td>{entity.confidence_score:.2f}</td>"
        f"<td>{entity.offset}</td>"
        f"<td>{entity.length}</td>"
        f"<td><code>{html.escape(entity.text)}</code></td>"
        "</tr>"
        for entity in entities
    )
    return (
        "<table><thead><tr><th>Category</th><th>Subcategory</th><th>Confidence</th>"
        f"<th>Offset</th><th>Length</th><th>Text</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def _highlight(text: str, entities: Sequence[PiiEntity]) -> str:
    parts: list[str] = []
    cursor = 0
    for entity in sorted(entities, key=lambda item: item.offset):
        end = entity.offset + entity.length
        if end <= cursor:
            continue
        start = max(cursor, entity.offset)
        parts.append(html.escape(text[cursor:start]))
        label = html.escape(entity.category)
        parts.append(f'<mark title="{label}">{html.escape(text[start:end])}</mark>')
        cursor = end
    parts.append(html.escape(text[cursor:]))
    return "".join(parts)


def _details(summary: str, body: str, href: str) -> str:
    return (
        f"<details><summary>{summary}</summary>"
        f'<p class="path"><a href="{href}">{href}</a></p>'
        f"<pre>{html.escape(body)}</pre></details>"
    )


def _pretty(payload: object) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(_pretty(payload), encoding=ENCODING)


def _page(run_id: str, images: int, emails: int, sections: Sequence[str]) -> str:
    body = "\n".join(sections) or '<p class="empty">Nothing was processed.</p>'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PII redaction trace {html.escape(run_id)}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font: 15px/1.5 system-ui, sans-serif; margin: 0 auto; max-width: 1200px; padding: 2rem; }}
h1 {{ margin-bottom: .25rem; }}
h2 {{ border-bottom: 1px solid #8884; padding-bottom: .4rem; }}
.meta, .path, .empty {{ color: #8a8a8a; font-size: .85rem; }}
.kind {{ background: #8883; border-radius: 4px; font-size: .7rem; padding: .1rem .4rem;
  text-transform: uppercase; vertical-align: middle; }}
section {{ margin-bottom: 3rem; }}
.strip {{ display: flex; gap: 1rem; overflow-x: auto; padding-bottom: .5rem; }}
.strip figure {{ flex: 0 0 auto; margin: 0; width: 280px; }}
.strip img {{ background: #fff; border: 1px solid #8884; border-radius: 6px; width: 100%; }}
.cols {{ display: grid; gap: 1rem; grid-template-columns: 1fr 1fr; }}
.cols figure {{ margin: 0; min-width: 0; }}
figcaption {{ font-size: .8rem; margin: .4rem 0; }}
pre {{ background: #8881; border-radius: 6px; margin: 0; max-height: 26rem; overflow: auto;
  padding: .75rem; }}
pre.text {{ white-space: pre-wrap; word-break: break-word; }}
mark {{ background: #ef444455; border-radius: 3px; }}
table {{ border-collapse: collapse; font-size: .85rem; margin: 1rem 0; width: 100%; }}
th, td {{ border-bottom: 1px solid #8883; padding: .35rem .5rem; text-align: left; }}
details {{ margin: .5rem 0; }}
summary {{ cursor: pointer; font-weight: 600; }}
</style>
</head>
<body>
<h1>PII redaction trace</h1>
<p class="meta">Run {html.escape(run_id)} &middot; {images} image(s) &middot; {emails} email(s)</p>
{body}
</body>
</html>
"""
