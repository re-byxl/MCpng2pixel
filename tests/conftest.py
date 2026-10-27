"""pytest 共享夹具。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
SRC_DIR = PROJECT_ROOT / "src"

# 让 tests.support.* 可以被直接导入
sys.path.insert(0, str(TESTS_DIR))

# 没装成包时也要能 import mcyqqs.*
if SRC_DIR.is_dir():
    sys.path.insert(0, str(SRC_DIR))

from support import (
    pipeline,  # noqa: E402
    reference,  # noqa: E402
)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def reference_image(tmp_path_factory) -> Path:
    """生成黄金样本用的参考图。"""
    path = tmp_path_factory.mktemp("reference") / "grid_sample.png"
    reference.write_reference(str(path))
    return path


@pytest.fixture(scope="session")
def golden_dir() -> Path:
    return TESTS_DIR / "golden"


@pytest.fixture(scope="session")
def pipeline_output(tmp_path_factory, reference_image):
    """跑一遍流水线，返回 (csv 文本, 方块文本)。"""
    workdir = tmp_path_factory.mktemp("pipeline")
    pipeline.run_pipeline(workdir, reference_image)
    csv_path = pipeline.find_output(workdir, ".csv")
    litematic_path = pipeline.find_output(workdir, ".litematic")
    return (
        csv_path.read_text(encoding="utf-8-sig"),
        pipeline.dump_blocks(litematic_path),
    )
