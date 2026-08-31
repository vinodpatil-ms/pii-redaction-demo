from collections.abc import Callable

import pytest

from pii_redaction_demo.core.config import Settings
from pii_redaction_demo.main import build_email_pipeline, build_image_pipeline


@pytest.mark.parametrize("build", [build_image_pipeline, build_email_pipeline])
def test_build_pipeline_requires_ai_services_endpoint(build: Callable[[Settings], object]) -> None:
    settings = Settings(_env_file=None, ai_services_endpoint=None)

    with pytest.raises(ValueError, match="APP_AI_SERVICES_ENDPOINT"):
        build(settings)
