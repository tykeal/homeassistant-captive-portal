# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0

# Captive Portal for Home Assistant

A production-ready captive portal solution for guest Wi-Fi networks, integrated with Home Assistant and TP-Link Omada controllers. Supports both voucher-based and booking-based (via Rental Control) guest authentication.

## Features

- **Dual Authentication**: Voucher codes or Home Assistant Rental Control booking identifiers
- **TP-Link Omada Integration**: Native support for Omada controller external portal API
- **Admin UI**: Role-based access control (RBAC) with viewer, auditor, operator, and admin roles
- **Audit Logging**: Comprehensive tracking of all admin actions and guest authentications
- **Rental Control Integration**: Automatic guest access based on booking check-in/check-out times
- **Resilient Operation**: Exponential backoff retry logic for controller communication
- **Security Hardened**: CSRF protection, rate limiting, secure session management, CSP headers
- **Performance Optimized**: In-memory caching, connection pooling, async operations
- **Flexible Vouchers**: Configurable length (4-24 chars), duration, and expiration policies

## Architecture Principles

1. **Defense in Depth**: Multiple validation layers, rate limiting, CSRF tokens, secure headers
2. **Fail Secure**: Controller unavailability blocks new grants; existing grants remain active
3. **Audit Trail**: All mutations logged with actor, action, target, outcome, and correlation ID
4. **Idempotent Operations**: Retry-safe controller interactions with deduplication
5. **Minimal Privilege**: RBAC denies by default; granular permission matrix per role
6. **Time Precision**: UTC-only timestamps with minute-level grant resolution
7. **Performance**: Sub-100ms p95 latency for voucher redemption under normal load

## Quick Start

### Home Assistant Add-on

1. Add repository: `https://github.com/tykeal/homeassistant-captive-portal`
2. Install "Captive Portal" from Add-on Store
3. Configure with your Omada controller credentials
4. Start and access admin UI at `http://<ha-ip>:8080/admin`

See [Quickstart Guide](docs/quickstart.md) for detailed setup instructions.

### Standalone Deployment

```bash
docker run -d \
  --name captive-portal \
  -p 8080:8080 \
  -v /path/to/data:/data \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=your_secure_password \
  -e OMADA_URL=https://192.168.1.10:8043 \
  -e OMADA_USERNAME=api_user \
  -e OMADA_PASSWORD=api_password \
  ghcr.io/tykeal/captive-portal:latest
```

## System Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Guest Device   │─────▶│  Captive Portal  │◀────▶│  TP-Omada       │
│  (Wi-Fi Client) │      │  (This Project)  │      │  Controller     │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                  │
                                  │ (Optional)
                                  ▼
                         ┌──────────────────┐
                         │ Home Assistant   │
                         │ + Rental Control │
                         └──────────────────┘
```

**Components**:
- **Guest Portal**: Unauthenticated endpoint for voucher/booking code submission
- **Admin UI**: RBAC-protected interface for voucher management, grant monitoring, configuration
- **TP-Omada Adapter**: Controller API client with retry/backoff resilience
- **HA Integration**: Rental Control entity polling service (60s interval, staleness detection)
- **Grant Service**: Orchestrates booking precedence, grant lifecycle, controller sync
- **Retry Queue**: Deferred persistence for failed controller operations (exponential backoff)

See [Architecture Overview](docs/architecture_overview.md) for detailed component diagrams and data flows.

## Documentation

- **[Quickstart Guide](docs/quickstart.md)**: Installation and initial configuration
- **[Admin UI Walkthrough](docs/admin_ui_walkthrough.md)**: Feature guide with screenshots
- **[TP-Omada Setup](docs/tp_omada_setup.md)**: Controller configuration and API access
- **[HA Integration Guide](docs/ha_integration_guide.md)**: Rental Control setup and troubleshooting
- **[Architecture Overview](docs/architecture_overview.md)**: System design and component interaction
- **[Troubleshooting](docs/troubleshooting.md)**: Common issues and diagnostics
- **[API Documentation](http://localhost:8080/docs)**: OpenAPI interactive docs (admin-only, when running)

## Configuration

Key configuration options (environment variables or add-on config):

| Option | Description | Default |
|--------|-------------|---------|
| `ADMIN_USERNAME` | Initial admin account username | `admin` |
| `OMADA_URL` | TP-Omada controller base URL | _(required)_ |
| `OMADA_SITE` | Omada site name | `Default` |
| `VOUCHER_LENGTH` | Default voucher code length | `10` |
| `RATE_LIMIT_ATTEMPTS` | Guest auth attempts per IP/minute | `5` |
| `SESSION_LIFETIME_HOURS` | Admin session duration | `24` |
| `CHECKOUT_GRACE_MINUTES` | Grace period after booking end | `15` |

See [docs/addon/config.md](docs/addon/config.md) for complete reference.

## Development

### Requirements

- Python 3.12+
- uv (recommended) or pip
- SQLite 3.35+

### Setup

```bash
git clone https://github.com/tykeal/homeassistant-captive-portal.git
cd homeassistant-captive-portal
uv sync
pre-commit install
```

### Running Tests

```bash
# Unit + integration tests
uv run pytest

# Type checking
uv run mypy src/ tests/

# Linting
pre-commit run -a
```

### Running Locally

```bash
cp .env.example .env
# Edit .env with your settings
uv run captive-portal
```

Access admin UI at `http://localhost:8080/admin`

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure `pre-commit run -a` passes
5. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## Security

- **Admin sessions**: HTTP-only, SameSite=Lax, 24h lifetime
- **CSRF protection**: All mutating endpoints require valid tokens
- **Rate limiting**: 5 auth attempts/minute/IP (configurable)
- **Audit logging**: All admin actions logged with correlation IDs
- **Password hashing**: Argon2id with secure defaults
- **Security headers**: CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy

Found a security issue? Email: tykeal@bardicgrove.org

## License

Apache-2.0 License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Home Assistant](https://www.home-assistant.io/)
- Supports [TP-Link Omada](https://www.tp-link.com/us/omada-sdn/) controllers
- Integrates with [Rental Control](https://github.com/tykeal/homeassistant-rental-control) custom component

## Support

- **Documentation**: [docs/](docs/)
- **Issues**: https://github.com/tykeal/homeassistant-captive-portal/issues
- **Discussions**: https://github.com/tykeal/homeassistant-captive-portal/discussions
