# Feature Specification: Multi-Device Vouchers

**Feature Branch**: `010-multi-device-vouchers`
**Created**: 2025-07-15
**Status**: Draft
**Input**: User description: "Allow vouchers to authorize N number of devices (defaulting to 1). Currently a voucher can only be claimed by a single device. This feature adds a max_devices field so a single voucher code can be used by multiple devices (e.g., a guest's phone, laptop, and tablet)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guest Redeems a Multi-Device Voucher (Priority: P1)

A guest arrives at a property and receives a single voucher code that allows them to connect multiple personal devices. The guest connects their first device (e.g., phone) to the WiFi network, gets redirected to the captive portal, and enters the voucher code. The system authorizes the device and indicates the voucher has remaining capacity. Later, the guest connects their laptop and tablet using the same voucher code, and each device is individually authorized. All devices gain internet access under the same voucher.

**Why this priority**: This is the core value proposition — enabling a single voucher to serve multiple devices. Without this, the feature has no purpose.

**Independent Test**: Can be fully tested by creating a multi-device voucher, then redeeming it from multiple devices in sequence. Delivers the primary value of reducing voucher management overhead for guests with multiple devices.

**Acceptance Scenarios**:

1. **Given** an admin has created a voucher with max_devices set to 3, **When** a guest enters the voucher code on their first device, **Then** the device is authorized and the voucher shows 1 of 3 devices used.
2. **Given** a voucher with max_devices of 3 that has been redeemed by 1 device, **When** the same guest enters the voucher code on a second device, **Then** the second device is authorized and the voucher shows 2 of 3 devices used.
3. **Given** a voucher with max_devices of 3 that has been redeemed by 3 devices, **When** a fourth device attempts to use the voucher code, **Then** the system rejects the attempt with a clear message indicating the voucher has reached its device limit.

---

### User Story 2 - Admin Creates a Multi-Device Voucher (Priority: P1)

An admin managing a small hotel or Airbnb property wants to create vouchers that can each serve multiple guest devices. Through the admin UI, the admin creates a new voucher and specifies the maximum number of devices it can authorize. The admin can also create vouchers in bulk, setting a shared max_devices value for all vouchers in the batch.

**Why this priority**: Admins must be able to create multi-device vouchers before guests can use them. This is a prerequisite for the guest experience and equally critical.

**Independent Test**: Can be tested by navigating to the admin voucher creation form, setting the max_devices field, and verifying the voucher is created with the correct capacity. Also testable via bulk creation.

**Acceptance Scenarios**:

1. **Given** an admin is on the voucher creation page, **When** the admin creates a voucher without specifying max_devices, **Then** the voucher is created with a default max_devices of 1 (backward compatible with current single-use behavior).
2. **Given** an admin is on the voucher creation page, **When** the admin sets max_devices to 5 and creates the voucher, **Then** the voucher is created and can be redeemed by up to 5 different devices.
3. **Given** an admin is creating a batch of vouchers, **When** the admin specifies max_devices for the batch, **Then** all vouchers in the batch are created with the specified max_devices value.
4. **Given** an admin is on the voucher creation page, **When** the admin attempts to set max_devices to 0 or a negative number, **Then** the system rejects the input and displays a validation error.

---

### User Story 3 - Admin Monitors Multi-Device Voucher Usage (Priority: P2)

An admin wants to see at a glance how many devices have redeemed each voucher and how much capacity remains. The admin views the voucher list in the admin UI and sees a usage indicator (e.g., "2/5 devices") for each multi-device voucher. This helps the admin understand which vouchers are fully used, partially used, or still unused.

**Why this priority**: Visibility into voucher usage is important for operational management but is not a blocking requirement for the core redeem flow.

**Independent Test**: Can be tested by creating vouchers with different max_devices values, redeeming some of them partially, and verifying the admin UI displays correct usage counts.

**Acceptance Scenarios**:

1. **Given** a voucher with max_devices of 5 has been redeemed by 2 devices, **When** an admin views the voucher list, **Then** the voucher displays "2/5 devices" as its usage status.
2. **Given** a voucher with max_devices of 1 that has been redeemed, **When** an admin views the voucher list, **Then** the voucher displays as fully redeemed (consistent with existing behavior).
3. **Given** a voucher with max_devices of 3 that has not been redeemed by any device, **When** an admin views the voucher list, **Then** the voucher displays "0/3 devices" as its usage status.

---

### User Story 4 - Backward-Compatible Single-Use Vouchers (Priority: P1)

Existing single-use voucher behavior must remain unchanged. Vouchers created before this feature (without a max_devices value) and newly created vouchers with the default max_devices of 1 must continue to work exactly as they do today — one device redeems the voucher and it becomes fully redeemed.

**Why this priority**: Backward compatibility is critical to avoid breaking existing deployments and workflows.

**Independent Test**: Can be tested by creating a voucher with max_devices of 1 (or the default), redeeming it with one device, and confirming a second device is rejected. Also verified by ensuring existing vouchers without the field behave as single-use.

**Acceptance Scenarios**:

1. **Given** a voucher created with the default max_devices of 1, **When** a guest redeems it with one device, **Then** the voucher is marked as fully redeemed.
2. **Given** a voucher created with max_devices of 1 that has been redeemed, **When** a second device attempts to use it, **Then** the system rejects the attempt with the existing "voucher already redeemed" behavior.
3. **Given** a voucher that existed before this feature was introduced (no max_devices field), **When** the system evaluates it, **Then** the voucher is treated as having max_devices of 1.

---

### Edge Cases

- What happens when two devices attempt to redeem the last available slot on a voucher at the same time? The system must handle this atomically — only one device should succeed, the other should receive a "voucher fully redeemed" message.
- What happens when a grant associated with a multi-device voucher is revoked by an admin? The revoked grant should not count toward the device limit, freeing up a slot for another device.
- What happens when a guest tries to redeem a voucher from a device that has already been authorized by the same voucher? The system should recognize the device is already authorized and inform the guest rather than consuming an additional slot.
- What happens when an admin sets max_devices to an extremely large number (e.g., 999999)? The system should accept it but the admin UI should still display the usage count accurately.
- What happens when a voucher has expired but still has unused device slots? Expiration takes precedence — the voucher should be rejected regardless of remaining capacity.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support a configurable maximum number of devices per voucher, expressed as a positive integer with a minimum value of 1.
- **FR-002**: System MUST default the maximum devices to 1 when no value is specified during voucher creation, preserving backward compatibility.
- **FR-003**: System MUST track the number of distinct devices that have redeemed each voucher by counting grants with status `pending` or `active` associated with that voucher.
- **FR-004**: System MUST allow a voucher to be redeemed by additional devices as long as the number of active grants is less than the voucher's maximum devices value.
- **FR-005**: System MUST reject a voucher redemption attempt when the number of active grants has reached the voucher's maximum devices value, displaying a clear message to the guest.
- **FR-006**: System MUST handle concurrent redemption attempts atomically to prevent exceeding the maximum devices limit due to race conditions.
- **FR-007**: System MUST treat revoked grants as not counting toward the device limit, effectively freeing the slot for another device.
- **FR-008**: System MUST recognize when a device that is already authorized under a voucher attempts to redeem it again, and inform the guest that their device is already authorized rather than consuming an additional slot.
- **FR-009**: System MUST allow admins to specify the maximum devices value when creating an individual voucher through the admin UI.
- **FR-010**: The system SHALL provide a bulk voucher creation interface allowing admins to create N vouchers with shared parameters including max_devices. This introduces the bulk-create capability; only bulk revoke and bulk delete exist today.
- **FR-011**: System MUST validate that the maximum devices value is a positive integer (minimum 1) during voucher creation and reject invalid values with a clear error.
- **FR-012**: System MUST display the current device usage for each voucher in the admin voucher list, showing the count of active grants versus the maximum devices (e.g., "2/5 devices").
- **FR-013**: System MUST treat existing vouchers that predate this feature (with no max_devices value) as having a max_devices of 1.
- **FR-014**: System MUST continue to enforce all existing voucher validation rules (expiration, revocation) before evaluating device capacity.

### Key Entities

- **Voucher**: Represents an authorization code that grants network access. Key attributes: code, duration, optional VLAN restriction, maximum number of devices allowed, creation date, expiration status. A voucher can be associated with zero to many access grants.
- **Access Grant**: Represents an individual device authorization. Key attributes: device identifier (MAC address), associated voucher, authorization timestamp, revocation status. Each grant represents one device's use of a voucher.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Guests can connect up to the configured number of devices using a single voucher code, with each device gaining network access within the same time frame as a single-device voucher (under 30 seconds from code entry to authorization).
- **SC-002**: Existing single-use vouchers (max_devices=1) exhibit no observable difference in functional behavior. The duplicate-device error message is updated for all vouchers to use device-oriented language.
- **SC-003**: When two devices simultaneously attempt to claim the last available slot on a voucher, exactly one succeeds and the other receives a rejection — the system never authorizes more devices than the configured maximum.
- **SC-004**: Admins can determine the current usage status of any multi-device voucher (devices used vs. maximum) at a glance within the admin voucher list.
- **SC-005**: 100% of existing vouchers (created before this feature) continue to function as single-use vouchers without any manual migration or admin action.
- **SC-006**: Bulk voucher creation with a specified max_devices value completes successfully, with all vouchers in the batch configured identically.

## Assumptions

- Existing vouchers that predate this feature will be treated as having max_devices of 1 without requiring a data migration step; the system will apply this default at read time.
- The maximum number of devices per voucher does not have an enforced upper bound beyond being a positive integer; admins are trusted to set reasonable values.
- Each device is uniquely identified by its MAC address, consistent with the existing Omada controller authorization model.
- The duration/expiration of a voucher applies to the voucher itself, not individually per device — all devices authorized under the same voucher share the same expiration window.
- The guest-facing captive portal does not need to display the remaining device count to the guest; it only needs to inform them if the voucher is fully redeemed.
- The Omada External Portal API authorization call remains per-device (one call per MAC address); this feature does not change the authorization mechanism, only the voucher-level tracking.
