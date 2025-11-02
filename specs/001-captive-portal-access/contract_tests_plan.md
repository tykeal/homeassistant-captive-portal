<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract Tests Validation Plan

## Overview

There are currently 21 contract tests that are skipped because they require live integration with external systems (TP-Omada Controller and Home Assistant). These tests validate the interaction contracts between the captive portal and external systems.

## Current Status

### Skipped Contract Tests (21 total)

#### Home Assistant Integration Tests (5 tests)
Located in `tests/contract/ha/test_entity_discovery.py`:
- `test_ha_entity_discovery_request` - Validates REST API request structure
- `test_ha_entity_discovery_response_structure` - Validates response format
- `test_ha_entity_event_attributes_validation` - Validates event entity attributes
- `test_ha_entity_discovery_unavailable` - Tests error handling when HA is unreachable
- `test_ha_entity_discovery_empty_result` - Tests handling of no matching entities

**Skip Reason**: "HA client not implemented yet" (Note: Client IS implemented, tests need updating)

#### TP-Omada Controller Tests (16 tests)

**Authorize Flow** (`tests/contract/tp_omada/test_authorize_flow.py` - 5 tests):
- `test_omada_authorize_request_structure` - Validates request payload schema
- `test_omada_authorize_response_success` - Validates successful response parsing
- `test_omada_authorize_response_error` - Validates error response handling
- `test_omada_authorize_retry_on_timeout` - Tests retry logic with exponential backoff
- `test_omada_authorize_idempotent` - Tests idempotent behavior

**Revoke Flow** (`tests/contract/tp_omada/test_revoke_flow.py` - 5 tests):
- `test_omada_revoke_request_structure` - Validates request payload schema
- `test_omada_revoke_response_success` - Validates successful response parsing
- `test_omada_revoke_response_not_found` - Tests handling of non-existent grants
- `test_omada_revoke_retry_on_timeout` - Tests retry logic
- `test_omada_revoke_idempotent` - Tests idempotent behavior

**Error Retry** (`tests/contract/tp_omada/test_adapter_error_retry.py` - 6 tests):
- `test_authorize_retries_on_connection_error` - Tests retry on connection failures
- `test_authorize_fails_after_max_retries` - Tests max retry limit
- `test_authorize_does_not_retry_on_4xx_errors` - Tests no retry on client errors
- `test_authorize_retries_on_5xx_errors` - Tests retry on server errors
- `test_revoke_retries_on_timeout` - Tests retry on timeout
- `test_exponential_backoff_timing` - Validates backoff timing

**Skip Reason**: "Controller adapter not implemented yet" or "TDD red: adapter not implemented"
(Note: Adapter IS implemented in Phase 3, tests need updating)

## Implementation Status

### What's Been Implemented

1. **HA Client** (`src/captive_portal/integrations/ha_client.py`):
   - REST API client for Home Assistant
   - Entity discovery and attribute extraction
   - Error handling and retry logic
   - Implemented in Phase 5

2. **TP-Omada Adapter** (`src/captive_portal/controllers/tp_omada/adapter.py`):
   - Authorization and revocation flows
   - Retry logic with exponential backoff
   - Error handling for various HTTP status codes
   - Idempotent operations
   - Implemented in Phase 3

3. **BookingCodeValidator** (`src/captive_portal/services/booking_code_validator.py`):
   - Integration with HA client
   - Booking code validation logic
   - Event window checking
   - Implemented in Phase 5

### What's Missing for Contract Test Execution

Contract tests require **live external systems** to validate actual integration contracts:

1. **TP-Omada Controller**:
   - Actual TP-Omada SDN Controller instance
   - Valid site ID and controller credentials
   - Network connectivity from test environment

2. **Home Assistant Instance**:
   - Running Home Assistant instance
   - Rental Control integration installed and configured
   - Sample booking data for testing
   - Long-lived access token

## Validation Approaches

### Option A: Docker Compose Test Stack (Recommended)

Create a `docker-compose.test.yml` that provides:

1. **Home Assistant Container**:
   ```yaml
   services:
     homeassistant:
       image: homeassistant/home-assistant:latest
       volumes:
         - ./test-fixtures/ha-config:/config
       ports:
         - "8123:8123"
   ```

2. **Mock Rental Control Integration**:
   - Custom integration that mimics Rental Control entity structure
   - Pre-seeded with test booking data
   - Controlled attributes for deterministic testing

3. **Mock TP-Omada API**:
   - Simple Flask/FastAPI mock server
   - Implements authorize/revoke endpoints
   - Returns predictable responses for testing
   - Located in `tests/mocks/omada_server.py`

**Benefits**:
- Runs in CI/CD pipeline
- Deterministic and repeatable
- No external dependencies
- Fast execution

**Limitations**:
- Not testing against real Omada API
- Mock may not catch all edge cases
- Requires maintenance to match API changes

### Option B: Integration Environment

Set up a dedicated integration test environment:

1. **Real TP-Omada Controller**:
   - Dedicated hardware or VM
   - Test-only site configuration
   - Isolated from production

2. **Real Home Assistant**:
   - Dedicated instance for testing
   - Rental Control integration with test data
   - Automated reset between test runs

3. **Credentials Management**:
   - Environment variables for credentials
   - Vault or secrets manager
   - Never committed to repository

**Benefits**:
- Tests real integration behavior
- Catches actual API quirks
- High confidence in production compatibility

**Limitations**:
- Requires dedicated hardware/VMs
- Cannot run in standard CI without credentials
- Slower execution
- Less deterministic (external system states)

### Option C: Hybrid Approach (Recommended Long-term)

1. **Docker mocks for CI** (Option A)
2. **Manual validation against real systems** for major releases (Option B)
3. **Separate integration test suite** that runs on-demand

## Recommended Implementation Plan

### Phase 7 (Current)

1. ✅ **Document contract test status** (this document)
2. **Update skip reasons** in contract tests to reflect current implementation status
3. **Create mock Omada server** (`tests/mocks/omada_server.py`)
4. **Create HA fixture config** with mock Rental Control entities
5. **Implement docker-compose.test.yml**
6. **Un-skip and update contract tests** to use mocks

### Post-Phase 7 (Future Enhancement)

1. **Integration test environment** for real controller validation
2. **Manual test checklist** for release validation
3. **Documentation** for setting up integration test environment
4. **CI job** (optional, manual trigger) for integration environment

## Acceptance Criteria for Phase 7

For T0736 to be considered complete:

- [x] Contract test plan documented (this file)
- [ ] Mock TP-Omada server implemented
- [ ] Docker Compose test stack created
- [ ] Contract tests updated to use mocks
- [ ] All 21 contract tests passing with mocks
- [ ] CI integration validated
- [ ] Manual testing guide created for real controller validation

## Next Steps

1. Create mock Omada API server
2. Create HA test fixtures configuration
3. Implement docker-compose.test.yml
4. Update contract tests to use test infrastructure
5. Remove skip decorators and validate tests pass
6. Update CI to run contract tests

## Notes

- Contract tests use `@pytest.mark.contract` marker
- Can be run with: `pytest -m contract`
- Should be fast enough for regular CI execution with mocks
- Real integration testing should be part of release validation checklist
