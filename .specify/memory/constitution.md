<!--
  Sync Impact Report
  ==================================================
  Version change: 1.0.1 → 2.0.0
  Modified principles:
    - "I. Code Quality & Traceability" → "I. Code Quality (NON-NEGOTIABLE)"
      (expanded with docstring, type annotation, complexity requirements)
    - "II. Pre-Commit Integrity" → merged into
      "V. Atomic Commits & Compliance (NON-NEGOTIABLE)"
    - "III. Test-Driven Development & Phased Testing" → split into
      "II. Test-Driven Development (NON-NEGOTIABLE)" and
      "VI. Phased Development"
    - "IV. User Experience Consistency" → "III. User Experience Consistency"
      (resolved TODO, added captive-portal-specific UX rules)
    - "V. Performance & Efficiency Requirements" →
      "IV. Performance Requirements"
      (resolved TODO, added concrete baselines from spec)
  Added sections:
    - V. Atomic Commits & Compliance (NON-NEGOTIABLE) (consolidated)
    - VI. Phased Development (split from former III)
  Removed sections: None (restructured)
  Templates requiring updates:
    - .specify/templates/plan-template.md ✅ no change needed
    - .specify/templates/spec-template.md ✅ no change needed
    - .specify/templates/tasks-template.md ✅ no change needed
    - .specify/templates/checklist-template.md ✅ no change needed
    - .specify/templates/agent-file-template.md ✅ no change needed
    - AGENTS.md ✅ no change needed (defers to constitution)
  Follow-up TODOs: None (all prior TODOs resolved)
  ==================================================
-->

# Captive Portal Constitution

## Core Principles

### I. Code Quality (NON-NEGOTIABLE)

- All source code MUST pass configured linting and static analysis
  checks (ruff, mypy, interrogate) with zero errors or warnings.
- Every function and class MUST include a docstring that describes its
  purpose, parameters, return values, and raised exceptions.
- Type annotations MUST be present on all public function signatures.
- Code complexity MUST remain low; functions MUST NOT exceed a
  cyclomatic complexity of 10 (ruff rule C901). This limit MUST
  be enforced in the project's ruff configuration.
- All new source files MUST include SPDX license headers as defined
  in `REUSE.toml`. Files missing headers MUST NOT be committed.

### II. Test-Driven Development (NON-NEGOTIABLE)

- **Code-level TDD is mandatory.** Every unit of production code
  MUST be preceded by a failing test that defines the desired
  behavior. The Red-Green-Refactor cycle is strictly enforced:
  1. Write a failing test that defines the desired behavior.
  2. Implement the minimum code required to make the test pass.
  3. Refactor while keeping all tests green.
- **Phase-level test planning is incremental.** Not every test
  category (integration, end-to-end, performance) for a phase
  MUST be written before that phase begins. Higher-level tests
  that span multiple stories or depend on infrastructure from
  later phases MAY be deferred to the phase where their
  prerequisites exist. Unit-level TDD (the red-green-refactor
  cycle above) MUST NOT be deferred under any circumstance.
- CI tests MUST pass before any manual or exploratory testing is
  performed. Manual testing without green CI is prohibited.
- Test coverage MUST be maintained or increased with every change;
  coverage regressions MUST be justified and approved.

### III. User Experience Consistency

- The guest portal MUST present a consistent, themed experience
  across all captive detection entry points (Android, iOS, Windows,
  Firefox). Error messages MUST be actionable: they MUST describe
  what went wrong and suggest corrective steps where feasible.
- The admin interface MUST use consistent naming, layout, and
  interaction patterns. Deviations MUST include justification in
  the PR description.
- API contracts (OpenAPI schema, TP-Omada adapter payloads, HA REST
  client interfaces) MUST be documented and versioned. Breaking
  changes to API paths, request/response schemas, or configuration
  options MUST be documented and communicated before release.
- Configuration surfaces MUST use sensible defaults so that minimal
  setup is required for common use cases (e.g., a single Omada
  controller and one HA Rental Control integration).

### IV. Performance Requirements

- Voucher redemption MUST complete within 800ms p95 at 50 concurrent
  requests. Admin grant listing (500 grants) MUST complete within
  1500ms p95. Controller propagation MUST complete within 25s.
- Regressions against established baselines MUST block merge until
  resolved or explicitly justified.
- Resource consumption (memory, CPU, I/O) MUST be considered during
  design; the application MUST NOT impose excessive overhead on the
  host system during normal operation.
- Asynchronous operations MUST NOT block the FastAPI event loop;
  blocking calls MUST be offloaded to executor threads or use
  async-compatible libraries.

### V. Atomic Commits & Compliance (NON-NEGOTIABLE)

- Every commit MUST represent exactly one logical change (one feature,
  one fix, or one refactor).
- Any commit that introduces new files MUST include SPDX license
  headers for those files. Every commit MUST carry a DCO sign-off
  (`git commit -s`).
- Pre-commit hooks MUST pass on every commit. Bypassing hooks with
  `--no-verify` is **PROHIBITED** under all circumstances.
- Commit messages MUST follow Conventional Commits with capitalized
  types as defined in `AGENTS.md`.
- Task list updates MUST occur in a separate follow-up documentation
  commit after the functional/code commit(s) resolving the tasks.
  Reviewers SHALL reject combined code+task-closure commits.

### VI. Phased Development

- Development MUST proceed in defined phases; each phase delivers an
  independently testable increment of functionality.
- Tests for a phase MUST be written during that phase or a later
  phase, not all up front. This allows requirements to stabilize
  before tests are locked in.
- Each phase MUST conclude with a checkpoint where all CI tests pass
  and the increment is validated before the next phase begins.
- Phase boundaries MUST be documented in the implementation plan
  (`plan.md`) and task list (`tasks.md`).

## Additional Constraints

- **Language & Runtime**: Python 3.13+ with full type annotation
  coverage enforced by mypy.
- **Dependency Management**: Dependencies MUST be managed via `uv`
  with a locked dependency file (`uv.lock`) committed to the
  repository.
- **License Compliance**: The project follows the REUSE specification.
  Every file MUST be covered by an SPDX header or an entry in
  `REUSE.toml`.
- **Security**: Secrets MUST NOT be committed to source control.
  Credentials MUST be injected via environment variables or HA
  Supervisor configuration. Passwords MUST use Argon2 hashing with
  OWASP-recommended parameters.
- **Home Assistant Compatibility**: The add-on MUST follow Home
  Assistant add-on conventions and build successfully from the local
  Dockerfile within the HA Supervisor environment.
- **Observability**: Structured logs MUST be emitted for all error
  paths. Audit logging MUST record all admin and guest authorization
  actions with timestamps and actor identification.

## Development Workflow & Quality Gates

1. **Write tests** for the current phase or story (TDD red phase).
2. **Implement** the minimum code to pass those tests (TDD green).
3. **Refactor** while keeping all tests green.
4. **Run linting & type checks** locally (`ruff`, `mypy`).
5. **Stage and commit** atomically with sign-off and SPDX headers.
6. **Pre-commit hooks** run automatically — fix any failures and
   re-commit (do NOT reset; do NOT bypass).
7. **CI pipeline** MUST pass. No manual or exploratory testing is
   permitted until CI is green.
8. **Manual validation** may proceed only after CI confirms all
   automated checks pass.

## Governance

- This constitution supersedes all other development practices. In
  case of conflict, this document prevails.
- Amendments MUST be documented with a version bump, rationale, and
  migration plan if existing code is affected.
- Version increments follow semantic versioning:
  - **MAJOR**: Backward-incompatible principle removals or
    redefinitions.
  - **MINOR**: New principles or materially expanded guidance.
  - **PATCH**: Clarifications, wording, or non-semantic refinements.
- All pull requests and code reviews MUST verify compliance with
  these principles. Non-compliance MUST block merge.
- Exceptions: temporary waivers MUST include expiration date and
  mitigation task ID.
- Use `AGENTS.md` for runtime development guidance that supplements
  this constitution.

**Version**: 2.0.0 | **Ratified**: 2025-10-22 | **Last Amended**: 2026-03-24
