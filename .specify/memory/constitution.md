# Captive Portal Constitution
<!-- Project governance and non‑negotiable engineering standards -->

<!--
Sync Impact Report:
Version: 1.0.1 (patch)
Modified principles: Added task completion commit sequencing rule
Added sections: None
Removed sections: None
Templates requiring updates: .specify/templates/plan-template.md ✅ | .specify/templates/spec-template.md ⚠ (review UX & performance constraints) | .specify/templates/tasks-template.md ⚠ (ensure TDD checkpoints + separate completion commit rule) | README.md ⚠ (add principles summary) | .github/prompts/speckit.tasks.prompt.md ⚠ (reflect separate commit requirement)
Deferred TODOs: TODO(PERFORMANCE_BASELINES): define concrete p95 latency & resource targets; TODO(UX_PATTERN_LIBRARY): enumerate UX components & guidelines.
-->

## Core Principles

### I. Code Quality & Traceability
All code changes MUST be delivered as small atomic commits representing one logical change only.
Each new or modified source file MUST include a correct SPDX license identifier header.
Commits MUST reference an issue or task when applicable for auditability.
Lint, formatting, security (secret scan), and static analysis MUST pass before merge; critical findings CANNOT be waived without documented rationale.

### II. Pre-Commit Integrity (Non-Negotiable)
Pre-commit hooks (lint, formatting, security, tests selection) MUST run and pass locally prior to any push; bypassing hooks is PROHIBITED.
If a hook fails it MUST be fixed—temporary disabling is not allowed.
Tooling MUST be maintained so that hook execution time remains <30s median to avoid developer friction.

### III. Test-Driven Development & Phased Testing
Tests for a phase MUST be authored before implementing code for that phase (Red-Green-Refactor preserved).
Not all future-phase tests are required up front; later phases MAY add tests for earlier code ONLY if expanding scope—never retroactively weaken earlier coverage.
A new test MUST fail (red) prior to implementation and pass (green) after; refactors MUST keep all existing tests green.
CI tests MUST be green before any manual exploratory or UX testing begins.

### IV. User Experience Consistency
User-facing behaviors (API contract, UI flows, configuration semantics) MUST conform to a documented UX pattern set (TODO(UX_PATTERN_LIBRARY)).
Naming, error messages, and log formats MUST be consistent; deviations MUST include justification in the PR description.
Backward-incompatible UX changes REQUIRE a migration note and version bump where user-visible.

### V. Performance & Efficiency Requirements
Each feature MUST define measurable performance baselines (TODO(PERFORMANCE_BASELINES)).
Changes MUST NOT regress established baselines beyond agreed thresholds (e.g., >5% p95 latency increase) without explicit approval and mitigation plan.
Performance tests or benchmarks MUST be added for critical paths before declaring a phase complete.

## Additional Standards & Constraints
- Minimum test coverage for new code: ≥80% lines AND ≥90% of critical branches; waivers documented.
- Cyclomatic complexity target: ≤10 per function; exceptions require justification and follow-up task.
- No commented-out dead code; TODO/FIXME tags MUST link to issues.
- Security: secrets NEVER committed; dependency scanning integrated into CI.
- Observability: structured logs for all error paths; metrics added for performance baselines when feasible.
- Documentation: public APIs & user-visible behaviors MUST be documented alongside implementation.

## Development Workflow & Quality Gates
Phased Development: Research → Design/Data Model → Contracts → Implementation/User Stories → Polish.
Each phase entry requires passing Constitution Gates (see plan-template) and creation of phase-specific tests prior to feature code.
CI Pipeline Order: lint/format → static/security → unit → contract → integration/performance (as available); manual testing ONLY after all green.
Atomic Commit Rules: one feature/task per commit; revert commits MUST restore SPDX header integrity.
Review Checklist MUST verify: atomic commit scope, SPDX headers, TDD adherence (new tests existed pre-implementation), hook evidence (e.g., commit includes formatted code), performance baseline impact.

## Governance
This constitution supersedes informal practices; conflicts MUST be resolved in favor of the constitution.
Amendment Process: proposal PR including diff + rationale + version bump classification (MAJOR principles redefined; MINOR principle added/expanded; PATCH clarifications). Approval requires ≥2 maintainers.
Compliance Reviews: quarterly audit of coverage, complexity, performance baselines, and hook reliability—action items tracked as issues.
Enforcement:
- PR reviewers BLOCK merges on violations; repeated bypass attempts trigger maintainer escalation.
- Task list updates MUST occur in a separate follow-up documentation commit after the functional/code commit(s) resolving the tasks.
- Reviewers SHALL reject combined code+task-closure commits.
Versioning: semantic as above; automated tooling MAY verify no unexplained bracket tokens or missing SPDX headers before tagging.
Exceptions: temporary waivers MUST include expiration date and mitigation task ID.

**Version**: 1.0.1 | **Ratified**: 2025-10-22 | **Last Amended**: 2025-10-27
