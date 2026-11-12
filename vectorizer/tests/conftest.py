import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from archvec import synthetic  # noqa: E402


@pytest.fixture(scope="session")
def scan_pdf(tmp_path_factory):
    d = tmp_path_factory.mktemp("synthetic")
    p = d / "scan.pdf"
    truth = synthetic.write_scan_pdf(p, rotate_deg=0.8, seed=7)
    return p, truth


@pytest.fixture(scope="session")
def vector_pdf(tmp_path_factory):
    d = tmp_path_factory.mktemp("synthetic_vec")
    p = d / "vector.pdf"
    truth = synthetic.write_vector_pdf(p)
    return p, truth
