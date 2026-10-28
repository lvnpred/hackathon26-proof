"""Pure helpers of the load-test script (the script itself needs a running container)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "load"))
import run_load as L  # noqa: E402


def test_percentile_nearest_rank():
    data = [float(n) for n in range(1, 101)]
    assert (L.percentile(data, 50), L.percentile(data, 95)) == (50.0, 95.0)
    assert (L.percentile([], 95), L.percentile([7.0], 95)) == (0.0, 7.0)


@pytest.mark.parametrize("text,mib", [
    ("512MiB / 7.7GiB", 512.0), ("1.5GiB / 7GiB", 1536.0),                 # docker stats
    ("512MB / 4.1GB", 512 * 1e6 / 2**20), ("1.5GB / 4GB", 1.5 * 1e9 / 2**20),   # podman stats (decimal units)
    ("2048kB / 4GB", 2048 * 1e3 / 2**20), ("900B / 4GB", 900 / 2**20),
])
def test_parse_mem_mib(text, mib):
    assert L.parse_mem_mib(text) == pytest.approx(mib)


def test_parse_mem_mib_rejects_unknown_text():
    with pytest.raises(ValueError):
        L.parse_mem_mib("n/a")


def test_memory_growth_ignores_spikes_but_sees_a_rising_floor():
    assert L.memory_growth([400, 1500, 420, 1400, 410, 1600, 405, 1500, 415, 1450, 400, 1550])[0] <= 15
    grown, rel = L.memory_growth([400] * 8 + [450, 500, 700, 800])
    assert grown >= 200 and rel > 0.4


def _gate(**over):
    base = dict(total=100, status_5xx=0, other_failures=0, dictation_p95=2.0, saves=50,
                pdfs_written=50, mem_samples=[500.0] * 12)
    return L.evaluate_gate(**{**base, **over})


@pytest.mark.parametrize("over,word", [
    ({"status_5xx": 1}, "5xx"), ({"other_failures": 2}, "failed"), ({"total": 0}, "no requests"),
    ({"dictation_p95": L.P95_LIMIT_S + 0.1}, "p95"), ({"pdfs_written": 49}, "PDFs"),
    ({"mem_samples": [500.0]}, "memory samples"), ({"mem_samples": [400.0] * 10 + [900.0] * 2}, "memory grew"),
])
def test_gate_passes_a_healthy_run_and_fails_on_each_condition(over, word):
    assert _gate() == []
    assert any(word in p for p in _gate(**over))
