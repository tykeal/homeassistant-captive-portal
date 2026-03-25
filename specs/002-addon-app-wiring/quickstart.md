SPDX-FileCopyrightText: 2026 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0

# Quickstart: Addon Application Wiring

## Running as a Home Assistant Addon

### Prerequisites

- Home Assistant OS or Supervised installation
- Docker (managed by HA Supervisor)
- Supported architectures: amd64 or aarch64

### Installation

1. Add the repository to your Home Assistant addon store:
   - Navigate to **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
   - Add the repository URL

2. Find "Captive Portal Guest Access" in the addon store and click **Install**.

3. Configure the addon (optional — sensible defaults are provided):
   - **Log Level**: `info` (options: trace, debug, info, notice, warning,
     error, fatal)
   - **Session Idle Timeout**: `30` minutes
   - **Session Max Duration**: `8` hours

4. Click **Start**.

5. Open the Web UI (port 8080) to access the admin interface.

### Verifying the Addon

After starting, verify the application is running:

```bash
# Health check (should return {"status": "ok", ...})
curl http://<ha-host>:8080/api/health

# Readiness check (should return {"status": "ok", "checks": {"database": "ok"}, ...})
curl http://<ha-host>:8080/api/ready
```

Navigate to `http://<ha-host>:8080/admin/login` to access the admin interface.

### Configuration

Configuration is managed through the Home Assistant addon configuration panel.
Changes take effect after restarting the addon.

| Setting | Default | Description |
|---------|---------|-------------|
| Log Level | info | Application log verbosity |
| Session Idle Timeout | 30 | Minutes before idle admin sessions expire |
| Session Max Duration | 8 | Hours before admin sessions expire regardless of activity |

### Data Persistence

The addon stores its SQLite database at `/data/captive_portal.db` inside the
container. The `/data/` directory is a persistent volume managed by the HA
Supervisor — data survives addon restarts and upgrades.

---

## Running in Development (Without Home Assistant)

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Clone the repository
git clone <repo-url>
cd captive-portal

# Install dependencies
uv sync

# Run tests
uv run pytest tests/

# Start the application (development mode)
uv run uvicorn captive_portal.app:app --host 0.0.0.0 --port 8080 --reload
```

### Environment Variables

When running outside the addon container, configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CP_LOG_LEVEL` | `info` | Log verbosity (trace/debug/info/notice/warning/error/fatal) |
| `CP_DB_PATH` | `/data/captive_portal.db` | Path to SQLite database file |
| `CP_SESSION_IDLE_TIMEOUT` | `30` | Session idle timeout in minutes |
| `CP_SESSION_MAX_DURATION` | `8` | Session max duration in hours |

Example:

```bash
CP_LOG_LEVEL=debug CP_DB_PATH=./dev.db uv run uvicorn captive_portal.app:app \
  --host 0.0.0.0 --port 8080 --reload
```

### Running Tests

```bash
# All tests
uv run pytest tests/

# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# With coverage
uv run pytest tests/ --cov=captive_portal --cov-report=term-missing
```

---

## Building the Addon Docker Image Locally

```bash
# Build for local architecture
docker build \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest \
  -t captive-portal-addon \
  addon/

# Run the built image (simulating addon environment)
docker run -d \
  -p 8080:8080 \
  -v captive-portal-data:/data \
  --name captive-portal \
  captive-portal-addon

# Verify
curl http://localhost:8080/api/health
```
