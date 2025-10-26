# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Metrics instrumentation for captive portal operations.

Provides counters and histograms for:
- Authorization operations and latency
- HA polling errors and success
- Cleanup operation counts
- Booking code validation attempts
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Generator

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Metric types."""

    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"


@dataclass
class MetricValue:
    """Metric value with metadata."""

    name: str
    value: float
    metric_type: MetricType
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class MetricsCollector:
    """In-memory metrics collector.

    Future: Can be extended to export to Prometheus, OpenTelemetry, etc.
    """

    def __init__(self) -> None:
        """Initialize metrics collector."""
        self._counters: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._gauges: dict[str, float] = {}

    def increment_counter(
        self, name: str, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Metric name
            value: Increment amount (default 1.0)
            labels: Metric labels
        """
        key = self._make_key(name, labels or {})
        self._counters[key] = self._counters.get(key, 0.0) + value
        logger.debug(f"Metric counter incremented: {key} += {value}")

    def record_histogram(
        self, name: str, value: float, labels: dict[str, str] | None = None
    ) -> None:
        """Record a histogram value.

        Args:
            name: Metric name
            value: Observation value
            labels: Metric labels
        """
        key = self._make_key(name, labels or {})
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)
        logger.debug(f"Metric histogram recorded: {key} = {value}")

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric value.

        Args:
            name: Metric name
            value: Gauge value
            labels: Metric labels
        """
        key = self._make_key(name, labels or {})
        self._gauges[key] = value
        logger.debug(f"Metric gauge set: {key} = {value}")

    @contextmanager
    def time_operation(
        self, name: str, labels: dict[str, str] | None = None
    ) -> Generator[None, None, None]:
        """Context manager to time an operation and record histogram.

        Args:
            name: Metric name
            labels: Metric labels

        Yields:
            None
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.record_histogram(name, duration, labels)

    def get_counter(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current counter value.

        Args:
            name: Metric name
            labels: Metric labels

        Returns:
            Counter value (0.0 if not set)
        """
        key = self._make_key(name, labels or {})
        return self._counters.get(key, 0.0)

    def get_histogram_stats(
        self, name: str, labels: dict[str, str] | None = None
    ) -> dict[str, float]:
        """Get histogram statistics (min, max, avg, p50, p95, p99).

        Args:
            name: Metric name
            labels: Metric labels

        Returns:
            Dictionary of statistics
        """
        key = self._make_key(name, labels or {})
        values = self._histograms.get(key, [])

        if not values:
            return {
                "count": 0.0,
                "min": 0.0,
                "max": 0.0,
                "avg": 0.0,
                "p50": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        sorted_values = sorted(values)
        count = len(sorted_values)

        return {
            "count": float(count),
            "min": min(sorted_values),
            "max": max(sorted_values),
            "avg": sum(sorted_values) / count,
            "p50": self._percentile(sorted_values, count, 50),
            "p95": self._percentile(sorted_values, count, 95),
            "p99": self._percentile(sorted_values, count, 99),
        }

    @staticmethod
    def _percentile(sorted_values: list[float], count: int, p: float) -> float:
        """Calculate percentile from sorted values.

        Args:
            sorted_values: Pre-sorted list of values
            count: Number of values
            p: Percentile (0-100)

        Returns:
            Percentile value
        """
        idx = int(count * p / 100)
        return sorted_values[min(idx, count - 1)]

    def get_gauge(self, name: str, labels: dict[str, str] | None = None) -> float:
        """Get current gauge value.

        Args:
            name: Metric name
            labels: Metric labels

        Returns:
            Gauge value (0.0 if not set)
        """
        key = self._make_key(name, labels or {})
        return self._gauges.get(key, 0.0)

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._histograms.clear()
        self._gauges.clear()
        logger.info("All metrics reset")

    @staticmethod
    def _make_key(name: str, labels: dict[str, str]) -> str:
        """Create metric key from name and labels.

        Args:
            name: Metric name
            labels: Metric labels

        Returns:
            Composite key string
        """
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"


# Global metrics collector instance
metrics = MetricsCollector()


# Metric name constants
METRIC_AUTHORIZE_TOTAL = "authorize_operations_total"
METRIC_AUTHORIZE_LATENCY = "authorize_latency_seconds"
METRIC_REVOKE_TOTAL = "revoke_operations_total"
METRIC_POLL_ERRORS = "ha_poll_errors_total"
METRIC_POLL_SUCCESS = "ha_poll_success_total"
METRIC_CLEANUP_RECORDS = "cleanup_records_deleted_total"
METRIC_BOOKING_CODE_VALIDATION = "booking_code_validation_total"
METRIC_BOOKING_CODE_LATENCY = "booking_code_validation_latency_seconds"
METRIC_ACTIVE_GRANTS = "active_grants_count"
