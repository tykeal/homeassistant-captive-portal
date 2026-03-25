SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Phase 0 Research: Addon Application Wiring

## R1: Home Assistant Addon Options Mechanism

### Question

How does the HA Supervisor deliver addon configuration to the container, and
what is the contract for reading it?

### Decision

Read `/data/options.json` at startup. This file is written by the HA Supervisor
before the addon process starts and contains the JSON object matching the
`schema` defined in `config.json`. The file is guaranteed to exist when the
addon starts and is read-only from the addon's perspective.

### Rationale

This is the standard, documented mechanism for all HA addons. The Supervisor
validates user input against the schema before writing the file, so the addon
receives type-checked values. However, the addon must still handle edge cases
(e.g., schema evolution where old options files lack new fields) by falling
through to defaults.

### Alternatives Considered

- **Environment variables only**: Simpler but bypasses the HA configuration UI
  entirely. Users would need SSH access to configure the addon, violating HA
  addon conventions and user expectations.
- **Supervisor API at runtime**: Adds an HTTP dependency at startup. The
  options.json file approach is simpler, faster, and does not require network
  access.

---

## R2: Configuration Precedence Design

### Question

How should addon options, environment variables, and built-in defaults be
merged, especially when an addon option value is invalid?

### Decision

Three-tier precedence: addon options (highest) → environment variables → built-in
defaults (lowest). Implemented as a single `AppSettings` pydantic `BaseModel`
with a class method `load()` that:

1. Reads `/data/options.json` if it exists (addon mode).
2. For each field, attempts to use the addon option value first.
3. If the addon option is missing, empty, or fails type/range validation,
   falls through to the corresponding `CP_`-prefixed environment variable.
4. If the env var is also missing or invalid, uses the built-in default.
5. Logs a warning for each invalid addon option value, stating what was
   invalid and what effective value was used.

### Rationale

The spec (FR-009) explicitly requires per-field fallthrough on invalid addon
values — not a wholesale rejection of the options file. This means we cannot
use pydantic-settings' automatic env loading (which would apply env vars
globally, not per-field). A custom `load()` method gives precise control over
the per-field precedence chain.

### Alternatives Considered

- **pydantic-settings `BaseSettings`**: Provides automatic env var loading but
  its precedence model is all-or-nothing (env vars override all fields or none).
  Does not support per-field fallthrough when a single addon option is invalid.
  Would also add a new dependency (`pydantic-settings`).
- **Dataclass with manual parsing**: Loses pydantic's validation, type coercion,
  and serialization. More code, more bugs.
- **YAML config file**: Non-standard for HA addons. The Supervisor writes JSON.

---

## R3: Template Path Resolution in Installed Packages

### Question

The current codebase uses `Jinja2Templates(directory="src/captive_portal/web/templates")`
which is a relative path from the working directory. Inside the container, the
package is installed into a venv — the `src/` prefix no longer exists. How
should templates be located?

### Decision

Use `pathlib.Path(__file__).resolve().parent` relative navigation to compute
the template directory at import time. Specifically, in each route module that
uses templates:

```python
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "web" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
```

This resolves to the correct location whether running from the source tree
(`src/captive_portal/api/routes/` → `src/captive_portal/web/templates/`) or
from an installed package (`site-packages/captive_portal/api/routes/` →
`site-packages/captive_portal/web/templates/`).

### Rationale

`pathlib.Path(__file__)` is the standard Python approach for locating package
data files. It requires no additional dependencies, works in both development
and production, and is explicit about the directory relationship.

### Alternatives Considered

- **`importlib.resources`**: Designed for package data access but returns
  `Traversable` objects, not filesystem paths. Jinja2's `FileSystemLoader`
  requires a real directory path. Using `as_file()` context manager adds
  complexity for no benefit when the files are already on disk.
- **`pkg_resources`**: Deprecated in favor of `importlib.resources`. Slower
  startup due to metadata scanning.
- **Environment variable for template dir**: Adds configuration burden.
  The templates are always in a fixed location relative to the code.
- **Copy templates to a known absolute path in Dockerfile**: Fragile. Breaks
  the single-source-of-truth principle and requires Dockerfile maintenance
  when templates change.

---

## R4: Static File Serving

### Question

The project has CSS in `web/themes/default/admin.css` but no `StaticFiles`
mount. How should static assets be served in the addon?

### Decision

Add a `StaticFiles` mount in `create_app()` for the themes directory:

```python
from fastapi.staticfiles import StaticFiles

_THEMES_DIR = Path(__file__).resolve().parent / "web" / "themes"
app.mount("/static/themes", StaticFiles(directory=str(_THEMES_DIR)), name="themes")
```

Templates reference CSS via `/static/themes/default/admin.css`.

### Rationale

FastAPI's built-in `StaticFiles` is the standard approach. Mounting under
`/static/themes/` provides a clean URL namespace and allows future theme
additions without route conflicts.

### Alternatives Considered

- **Inline CSS in templates**: Increases HTML payload size and prevents
  browser caching. Current templates already reference external CSS.
- **Nginx reverse proxy**: Adds operational complexity. The addon runs a
  single process; FastAPI can serve its own static files efficiently at
  the expected scale (<50 concurrent users).
- **CDN**: Not viable — the addon runs on a local network without guaranteed
  internet access.

---

## R5: Graceful Shutdown

### Question

How does the addon container stop, and what cleanup is needed?

### Decision

Use FastAPI's lifespan context manager (or `shutdown` event) to close the
SQLAlchemy engine on application shutdown. Uvicorn handles SIGTERM by default:
it stops accepting new connections, waits for in-flight requests to complete
(with a configurable timeout), then shuts down the ASGI app.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB
    yield
    # Shutdown: dispose engine
    from captive_portal.persistence.database import dispose_engine
    dispose_engine()
```

The `dispose_engine()` function calls `engine.dispose()` which closes all
pooled connections.

### Rationale

The HA Supervisor sends SIGTERM to the container's PID 1 process and waits
up to 10 seconds before SIGKILL. Uvicorn's default graceful shutdown timeout
is 10 seconds, which aligns perfectly. The only resource requiring explicit
cleanup is the SQLAlchemy connection pool — in-memory session stores are
ephemeral and need no cleanup.

### Alternatives Considered

- **Signal handler in run.sh**: Bash signal traps are fragile with exec'd
  Python processes. Uvicorn already handles signals correctly.
- **atexit handler**: Not reliable in containerized environments where
  SIGKILL may follow SIGTERM quickly. The lifespan approach is invoked
  during uvicorn's orderly shutdown.
- **No explicit cleanup**: SQLite connections would eventually be GC'd, but
  relying on garbage collection risks WAL checkpoint issues and is not
  deterministic.

---

## R6: Dockerfile Package Installation Strategy

### Question

The current Dockerfile installs only `fastapi` and `uvicorn[standard]` via pip.
How should the full application with all dependencies be installed?

### Decision

Copy the project source into the container and install it as a package using
pip with the local project path. This installs all dependencies declared in
`pyproject.toml`:

```dockerfile
COPY pyproject.toml /app/
COPY src/ /app/src/

RUN "$VIRTUAL_ENV/bin/python" -m pip install --no-cache-dir /app
```

### Rationale

Installing the project as a package (rather than copying source and running
directly) ensures: (1) all dependencies from `pyproject.toml` are installed;
(2) the package is properly importable via `import captive_portal`; (3)
`setuptools` resolves the `package-dir` mapping correctly; (4) the installed
package layout matches what tests validate.

### Alternatives Considered

- **`uv` inside the container**: The Alpine base image doesn't include `uv`,
  and installing it adds build complexity. Standard pip works and is already
  available in the venv.
- **Copy source + `pip install -r requirements.txt`**: The project doesn't
  maintain a separate requirements.txt. Generating one adds a build step.
  `pip install .` reads `pyproject.toml` directly.
- **Multi-stage build with uv**: Viable for future optimization but
  over-engineering for the current scope. The single-stage pip install is
  straightforward and matches the existing Dockerfile pattern.

---

## R7: Addon Configuration Schema Design

### Question

What configuration options should be exposed in `config.json` schema, and
what are their types/defaults/constraints?

### Decision

Three options for the initial addon configuration:

| Option | Type | Default | Constraints | Maps to |
|--------|------|---------|-------------|---------|
| `log_level` | list(trace\|debug\|info\|notice\|warning\|error\|fatal) | `info` | HA standard log levels | Python logging level |
| `session_idle_timeout` | int | `30` | ≥1, minutes | `SessionConfig.idle_minutes` |
| `session_max_duration` | int | `8` | ≥1, hours | `SessionConfig.max_hours` |

### Rationale

These three options directly map to the spec's FR-007 requirements. Additional
options (Omada controller, HA credentials) are explicitly out of scope per the
spec's Assumptions section. The HA log level list follows the standard set used
by other HA addons.

### Alternatives Considered

- **Exposing all environment variables**: Too many options for initial release.
  Overwhelms the HA configuration UI. Better to add incrementally.
- **Database URL as config option**: Security risk (exposes file paths). The
  database location (`/data/captive_portal.db`) is a fixed convention.
- **Port as config option**: The addon's port mapping is handled by HA
  Supervisor via `config.json` ports, not application config.

---

## R8: Log Level Mapping

### Question

HA addons use a specific set of log levels (trace, debug, info, notice,
warning, error, fatal) that don't map 1:1 to Python's logging levels. How
should the mapping work?

### Decision

Map HA log levels to Python logging levels:

| HA Level | Python Level | `logging` constant |
|----------|--------------|--------------------|
| trace | DEBUG (5-level detail) | `logging.DEBUG` |
| debug | DEBUG | `logging.DEBUG` |
| info | INFO | `logging.INFO` |
| notice | INFO (treated as INFO) | `logging.INFO` |
| warning | WARNING | `logging.WARNING` |
| error | ERROR | `logging.ERROR` |
| fatal | CRITICAL | `logging.CRITICAL` |

Both `trace` and `debug` map to `logging.DEBUG` because Python has no TRACE
level by default. Both `info` and `notice` map to `logging.INFO` because
Python has no NOTICE level. Uvicorn's `--log-level` flag accepts: critical,
error, warning, info, debug, trace — the mapping handles this separately.

### Rationale

Minimal mapping complexity. Users who select "trace" in the HA UI get the
most verbose output (DEBUG). Users who select "notice" get standard INFO.
No custom log levels are needed.

### Alternatives Considered

- **Custom TRACE and NOTICE levels**: Adds complexity to every `logger.log()`
  call. Python's logging module supports custom levels but they're non-standard
  and confuse tools.
- **Passing raw strings to uvicorn**: Uvicorn accepts "trace" but the
  application's own loggers need standard Python levels. Two separate
  configurations would be needed.
