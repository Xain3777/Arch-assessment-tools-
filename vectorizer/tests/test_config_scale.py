import pytest

from archvec.config import Config
from archvec.scale import build_scale


def test_overrides_and_types(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text('[correct]\nsnap_distance_mm = 2.5\n[preprocess]\nthreshold = "adaptive"\n')
    cfg = Config.load(p, ["correct.merge_gap_mm=1", "export.formats=['dxf']", "preprocess.denoise=none"])
    assert cfg.correct.snap_distance_mm == 2.5 and cfg.correct.merge_gap_mm == 1.0
    assert isinstance(cfg.correct.merge_gap_mm, float)
    assert cfg.preprocess.threshold == "adaptive" and cfg.preprocess.denoise == "none"
    assert cfg.export.formats == ["dxf"]


def test_unknown_keys_rejected():
    with pytest.raises(ValueError):
        Config.load(None, ["correct.nonexistent=1"])
    with pytest.raises(ValueError):
        Config().update({"nosection": {}})


def test_scale_sources():
    assert not build_scale(Config().scale, 300).calibrated
    cfg = Config.load(None, ["scale.denominator=100"])
    sc = build_scale(cfg.scale, 300)
    assert sc.calibrated and abs(sc.mm_per_unit - 25.4 / 300 * 100) < 1e-9
    cfg = Config.load(None, ["scale.known_distance_px=[0, 0, 1181.1, 0]", "scale.known_distance_mm=10000",
                             "scale.denominator=50"])
    sc = build_scale(cfg.scale, 300)
    assert sc.source == "known-distance" and abs(sc.denominator - 100) < 0.1
    assert any("WARNING" in n for n in sc.notes)  # 1:50 contradicts the measurement
