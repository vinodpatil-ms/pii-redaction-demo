from collections.abc import Sequence

from azure.ai.vision.imageanalysis import ImageAnalysisClient
from azure.ai.vision.imageanalysis.models import ImageAnalysisResult, ImagePoint, VisualFeatures
from azure.core.credentials import TokenCredential
from azure.identity import DefaultAzureCredential

from pii_redaction_demo.domain.models import OcrResult, TextRegion


class AzureVisionOcrProvider:
    """Reads printed and handwritten text with the Azure AI Vision Read (OCR) feature."""

    def __init__(
        self,
        endpoint: str,
        credential: TokenCredential | None = None,
    ) -> None:
        # The accounts deployed by infra/terraform have local auth disabled, so Entra ID
        # tokens are the only supported data-plane credential.
        # Sync client for POC simplicity; an async client is available for production workloads.
        self._client = ImageAnalysisClient(
            endpoint=endpoint,
            credential=credential or DefaultAzureCredential(),
        )

    def read_image(self, image: bytes) -> OcrResult:
        result = self._client.analyze(image_data=image, visual_features=[VisualFeatures.READ])
        return _to_ocr_result(result)

    def close(self) -> None:
        self._client.close()


def _to_ocr_result(result: ImageAnalysisResult) -> OcrResult:
    blocks = result.read.blocks if result.read is not None else []
    regions = tuple(
        TextRegion(
            text=line.text,
            polygon=_to_polygon(line.bounding_polygon),
            words=tuple(
                TextRegion(text=word.text, polygon=_to_polygon(word.bounding_polygon))
                for word in line.words
            ),
        )
        for block in blocks
        for line in block.lines
    )
    return OcrResult(
        text="\n".join(region.text for region in regions),
        regions=regions,
        model_version=result.model_version,
    )


def _to_polygon(points: Sequence[ImagePoint]) -> tuple[tuple[int, int], ...]:
    return tuple((point.x, point.y) for point in points)
