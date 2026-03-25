<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Cache Decision Record (T0715)

## Status

**Decision: Keep caching layer (T0611) — retain for MVP with existing scope.**

## Context

Task T0611 introduced an in-memory TTL cache service
(`src/captive_portal/services/cache_service.py`) to reduce redundant
controller API round-trips. Task T0715 requires a formal decision on
whether to keep or remove this layer.

### Evidence Reviewed

| Artifact | Finding |
|---|---|
| `src/captive_portal/services/cache_service.py` | Async TTL cache with 30 s default, lock-based thread safety, explicit invalidation, pattern-based bust, and expired-entry cleanup. |
| `tests/unit/services/test_cache_service.py` | Unit tests already exist covering the service. |
| `src/captive_portal/models/rental_control_event.py` | DB-backed Rental Control event cache model (separate from in-memory cache). |
| `specs/001-captive-portal-access/spec.md` | Mentions fallback to "cached authorization assumptions" when HA entity data is temporarily unavailable. |
| Tasks addenda (line 290) | Recommends 30–60 s controller status TTL, 5–10 m HA metadata TTL, explicit bust on mutations. |
| Usage in other modules | `CacheService` / `get_cache` are **not yet imported** outside `cache_service.py` — the layer exists but is not wired into request paths. |

## Decision Rationale

1. **Code is already written and tested.** Removing T0611 would delete
   working, tested code with no tangible benefit. The implementation is
   small (~120 LOC) and self-contained.

2. **Spec supports it.** The spec explicitly calls for fallback to
   cached data during HA unavailability, validating the need for a
   caching abstraction.

3. **Low integration risk.** The cache service is not yet wired into
   production request paths — it is an optional layer that can be
   adopted incrementally when controller or HA round-trip latency is
   measured.

4. **NFR alignment.** The tasks addenda recommend a ~35 % (revised from original 60 %) reduction in
   controller round-trips via caching. The existing 30 s TTL default
   matches the recommended 30–60 s window for controller status.

5. **No premature optimization concern.** Because the cache is not yet
   in the hot path, keeping it does not add runtime complexity to MVP.
   It provides a ready-made building block for post-MVP performance
   tuning.

## Conditions for Full Activation

Before wiring `CacheService` into request handlers:

- Establish baseline controller round-trip latency via the performance
  validation guide (`docs/performance_validation_guide.md`).
- Confirm that caching yields ≥ 35 % (revised from 60 %) reduction in controller API calls
  under representative load.
- Add integration tests validating cache-hit / cache-miss / invalidation
  paths in the request lifecycle.
- Implement explicit cache bust on grant create / update / delete
  mutations to prevent stale authorization data.

## Outcome

- **T0611 retained** — no code removed.
- **NFR target** (reduce controller round-trips ≥ 35 % (revised from 60 %)) documented as a
  post-MVP activation gate.
- Cache activation deferred until baseline benchmarks are available.
