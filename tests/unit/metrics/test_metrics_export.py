# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""T0717 – Unit tests for metrics instrumentation.

Validates:
- active_sessions gauge tracking
- controller_latency histogram recording
- auth_failures counter tracking
- Metric export snapshot generation
"""

from __future__ import annotations

import time

import pytest

from captive_portal.utils.metrics import (
    METRIC_ACTIVE_SESSIONS,
    METRIC_AUTH_FAILURES,
    METRIC_CONTROLLER_LATENCY,
    MetricsCollector,
)


@pytest.fixture
def collector() -> MetricsCollector:
    """Fresh metrics collector for each test."""
    return MetricsCollector()


class TestActiveSessionsGauge:
    """Test active_sessions gauge metric."""

    def test_initial_value_is_zero(self, collector: MetricsCollector) -> None:
        """Unset gauge defaults to 0."""
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 0.0

    def test_set_active_sessions(self, collector: MetricsCollector) -> None:
        """set_gauge records the current session count."""
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 42.0)
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 42.0

    def test_gauge_overwrites_previous(self, collector: MetricsCollector) -> None:
        """Setting gauge replaces old value."""
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 10.0)
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 3.0)
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 3.0

    def test_gauge_with_labels(self, collector: MetricsCollector) -> None:
        """Labels create separate gauge series."""
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 5.0, labels={"controller": "omada"})
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 8.0, labels={"controller": "unifi"})
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS, labels={"controller": "omada"}) == 5.0
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS, labels={"controller": "unifi"}) == 8.0

    def test_gauge_zero_is_valid(self, collector: MetricsCollector) -> None:
        """Setting gauge to 0 is a valid observation (not same as unset)."""
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 10.0)
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 0.0)
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 0.0


class TestControllerLatencyHistogram:
    """Test controller_latency histogram metric."""

    def test_empty_histogram_stats(self, collector: MetricsCollector) -> None:
        """No observations yields zero-value stats."""
        stats = collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)
        assert stats["count"] == 0.0
        assert stats["p95"] == 0.0

    def test_single_observation(self, collector: MetricsCollector) -> None:
        """Single observation populates all stats."""
        collector.record_histogram(METRIC_CONTROLLER_LATENCY, 0.025)
        stats = collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)
        assert stats["count"] == 1.0
        assert stats["min"] == 0.025
        assert stats["max"] == 0.025

    def test_multiple_observations_percentiles(self, collector: MetricsCollector) -> None:
        """p95 computed from sorted observations."""
        # Record 100 values: 0.01, 0.02, ... 1.00
        for i in range(1, 101):
            collector.record_histogram(METRIC_CONTROLLER_LATENCY, i * 0.01)
        stats = collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)
        assert stats["count"] == 100.0
        assert stats["min"] == pytest.approx(0.01)
        assert stats["max"] == pytest.approx(1.0)
        # p95 for 0.01..1.00 in steps of 0.01 should be ~0.95
        assert stats["p95"] == pytest.approx(0.955, abs=0.02)

    def test_time_operation_records_histogram(self, collector: MetricsCollector) -> None:
        """time_operation context manager records elapsed time."""
        with collector.time_operation(METRIC_CONTROLLER_LATENCY):
            time.sleep(0.01)
        stats = collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)
        assert stats["count"] == 1.0
        assert stats["min"] > 0.0

    def test_histogram_with_labels(self, collector: MetricsCollector) -> None:
        """Labels isolate histogram series."""
        collector.record_histogram(METRIC_CONTROLLER_LATENCY, 0.1, labels={"endpoint": "authorize"})
        collector.record_histogram(METRIC_CONTROLLER_LATENCY, 0.5, labels={"endpoint": "revoke"})
        auth_stats = collector.get_histogram_stats(
            METRIC_CONTROLLER_LATENCY, labels={"endpoint": "authorize"}
        )
        revoke_stats = collector.get_histogram_stats(
            METRIC_CONTROLLER_LATENCY, labels={"endpoint": "revoke"}
        )
        assert auth_stats["count"] == 1.0
        assert revoke_stats["count"] == 1.0
        assert auth_stats["max"] == pytest.approx(0.1)
        assert revoke_stats["max"] == pytest.approx(0.5)


class TestAuthFailuresCounter:
    """Test auth_failures counter metric."""

    def test_initial_counter_is_zero(self, collector: MetricsCollector) -> None:
        """Unset counter defaults to 0."""
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 0.0

    def test_increment_counter(self, collector: MetricsCollector) -> None:
        """Increment adds to counter."""
        collector.increment_counter(METRIC_AUTH_FAILURES)
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 1.0

    def test_increment_counter_multiple(self, collector: MetricsCollector) -> None:
        """Multiple increments accumulate."""
        for _ in range(5):
            collector.increment_counter(METRIC_AUTH_FAILURES)
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 5.0

    def test_increment_by_custom_value(self, collector: MetricsCollector) -> None:
        """Increment with custom value."""
        collector.increment_counter(METRIC_AUTH_FAILURES, value=3.0)
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 3.0

    def test_counter_with_labels(self, collector: MetricsCollector) -> None:
        """Labels create separate counter series."""
        collector.increment_counter(METRIC_AUTH_FAILURES, labels={"reason": "bad_password"})
        collector.increment_counter(METRIC_AUTH_FAILURES, labels={"reason": "bad_password"})
        collector.increment_counter(METRIC_AUTH_FAILURES, labels={"reason": "account_locked"})
        assert collector.get_counter(METRIC_AUTH_FAILURES, labels={"reason": "bad_password"}) == 2.0
        assert (
            collector.get_counter(METRIC_AUTH_FAILURES, labels={"reason": "account_locked"}) == 1.0
        )


class TestMetricsExportSnapshot:
    """Test metrics export / snapshot capabilities."""

    def test_reset_clears_all_metrics(self, collector: MetricsCollector) -> None:
        """reset() clears counters, histograms, and gauges."""
        collector.increment_counter(METRIC_AUTH_FAILURES)
        collector.record_histogram(METRIC_CONTROLLER_LATENCY, 0.5)
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 10.0)
        collector.reset()
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 0.0
        assert collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)["count"] == 0.0
        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 0.0

    def test_all_three_metric_types_coexist(self, collector: MetricsCollector) -> None:
        """Counter, histogram, and gauge can be tracked simultaneously."""
        collector.set_gauge(METRIC_ACTIVE_SESSIONS, 7.0)
        collector.record_histogram(METRIC_CONTROLLER_LATENCY, 0.123)
        collector.increment_counter(METRIC_AUTH_FAILURES)

        assert collector.get_gauge(METRIC_ACTIVE_SESSIONS) == 7.0
        assert collector.get_histogram_stats(METRIC_CONTROLLER_LATENCY)["count"] == 1.0
        assert collector.get_counter(METRIC_AUTH_FAILURES) == 1.0

    def test_global_singleton_exists(self) -> None:
        """Module-level metrics singleton is importable."""
        from captive_portal.utils.metrics import metrics

        assert isinstance(metrics, MetricsCollector)
