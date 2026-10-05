import pytest

from app.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="pruebas",
        api_prefix="/api/v1",
        cors_origins=[],
    )
