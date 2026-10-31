import pytest
from benchmarks.stream_latency import check_budget, percentile


def test_nearest_rank_p95_includes_slow_tail():
    assert percentile(list(range(1, 101)), 0.95) == 95


def test_latency_budget_rejects_regression_and_missing_samples():
    report = {'failures': 0, 'samples': 100, 'expected_samples': 100, 'p95_ms': 600}
    with pytest.raises(AssertionError, match='exceeds'):
        check_budget(report, 500)
    report.update(p95_ms=100, samples=99)
    with pytest.raises(AssertionError, match='Incomplete'):
        check_budget(report, 500)
