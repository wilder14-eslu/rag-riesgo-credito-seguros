"""Fixtures compartidas: índice construido sobre el corpus de ejemplo en un directorio temporal."""

from __future__ import annotations

from pathlib import Path

import pytest

from riskrag.config import PROJECT_ROOT, Settings
from riskrag.factory import Services, build_index, build_services

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample"


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    tmp: Path = tmp_path_factory.mktemp("riskrag")
    return Settings(
        env="local",
        index_path=tmp / "index.json",
        audit_log_path=tmp / "audit.jsonl",
        api_keys_sha256=[],
    )


@pytest.fixture(scope="session")
def services(settings: Settings) -> Services:
    report = build_index(SAMPLE_DIR, settings)
    assert report.chunks > 0
    return build_services(settings)
