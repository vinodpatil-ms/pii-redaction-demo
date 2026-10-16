import argparse
import logging
import sys
from pathlib import Path

from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from pii_redaction_demo.core.config import PROJECT_ROOT, Settings, get_settings
from pii_redaction_demo.providers.azure_document_intelligence import (
    AzureDocumentIntelligenceOcrProvider,
)
from pii_redaction_demo.providers.azure_language import AzureLanguagePiiProvider
from pii_redaction_demo.providers.pillow_image import PillowImageRedactor
from pii_redaction_demo.services.pii_redaction import PiiRedactionService
from pii_redaction_demo.services.pipeline import (
    EmailRedactionPipeline,
    ImageRedactionPipeline,
    RedactedEmail,
    RedactedImage,
)
from pii_redaction_demo.services.trace_report import write_trace

LOG_FORMAT = "%(levelname)-7s %(name)s: %(message)s"

logger = logging.getLogger(__name__)


def build_image_pipeline(
    settings: Settings,
    credential: TokenCredential | None = None,
) -> ImageRedactionPipeline:
    endpoint = _require_endpoint(settings)
    if not settings.document_intelligence_endpoint:
        raise ValueError("APP_DOCUMENT_INTELLIGENCE_ENDPOINT is not configured")
    credential = credential or DefaultAzureCredential()
    return ImageRedactionPipeline(
        ocr=AzureDocumentIntelligenceOcrProvider(
            settings.document_intelligence_endpoint, credential
        ),
        redaction=_build_redaction_service(settings, endpoint, credential),
        image_redactor=PillowImageRedactor(),
    )


def build_email_pipeline(
    settings: Settings,
    credential: TokenCredential | None = None,
) -> EmailRedactionPipeline:
    endpoint = _require_endpoint(settings)
    credential = credential or DefaultAzureCredential()
    return EmailRedactionPipeline(
        redaction=_build_redaction_service(settings, endpoint, credential)
    )


def _build_redaction_service(
    settings: Settings,
    endpoint: str,
    credential: TokenCredential,
) -> PiiRedactionService:
    return PiiRedactionService(
        AzureLanguagePiiProvider(endpoint, credential),
        language=settings.pii_language,
        min_confidence=settings.pii_min_confidence,
    )


def _require_endpoint(settings: Settings) -> str:
    if not settings.ai_services_endpoint:
        raise ValueError("APP_AI_SERVICES_ENDPOINT is not configured")
    return settings.ai_services_endpoint


def main() -> None:
    settings = get_settings()
    args = _parse_args(settings)

    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if args.verbose else settings.log_level.upper(),
        format=LOG_FORMAT,
    )

    # One credential for both data planes, so the Entra ID token is acquired and cached once.
    credential = DefaultAzureCredential()

    images: list[RedactedImage] = []
    emails: list[RedactedEmail] = []

    if args.mode in ("images", "all"):
        images = build_image_pipeline(settings, credential).run(
            _resolve(args.input_dir),
            _resolve(args.output_dir),
        )

    if args.mode in ("emails", "all"):
        emails = build_email_pipeline(settings, credential).run(
            _resolve(args.email_input_dir),
            _resolve(args.email_output_dir),
        )

    masked = sum(len(item.entities) for item in images) + sum(len(item.entities) for item in emails)
    logger.info(
        "done: %d image(s), %d email(s), %d PII entity(ies) masked",
        len(images),
        len(emails),
        masked,
    )

    if args.trace:
        report = write_trace(
            _resolve(args.trace_dir),
            images=images,
            emails=emails,
            annotator=PillowImageRedactor(),
        )
        logger.info("trace report -> %s", report)


def _parse_args(settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Redact PII found in images and emails.")
    parser.add_argument("--mode", choices=("images", "emails", "all"), default="all")
    parser.add_argument("--input-dir", default=settings.input_images_dir)
    parser.add_argument("--output-dir", default=settings.output_images_dir)
    parser.add_argument("--email-input-dir", default=settings.input_emails_dir)
    parser.add_argument("--email-output-dir", default=settings.output_emails_dir)
    parser.add_argument(
        "--trace",
        action="store_true",
        help="write per-step artifacts and a side-by-side report.html under --trace-dir",
    )
    parser.add_argument("--trace-dir", default=settings.trace_dir)
    parser.add_argument("--verbose", action="store_true", help="log at DEBUG level")
    return parser.parse_args()


def _resolve(directory: str) -> Path:
    path = Path(directory)
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    main()
