<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg
SPDX-License-Identifier: Apache-2.0
-->

# Admin UI Walkthrough

Welcome to the Captive Portal administration interface. This guide walks you
through every screen and feature so you can confidently manage guest Wi-Fi
access for your property. No technical background is required — just follow
along step by step.

> **Tip:** For the overall system design and how the pieces fit together, see
> [Architecture Overview](architecture_overview.md).

---

## Table of Contents

1. [Logging In](#logging-in)
2. [Dashboard Overview](#dashboard-overview)
3. [Grant Management](#grant-management)
4. [Voucher Generation and Management](#voucher-generation-and-management)
5. [Entity Mapping (Integrations)](#entity-mapping-integrations)
6. [Configuration Management](#configuration-management)
7. [Audit Log Access and Filtering](#audit-log-access-and-filtering)
8. [API Documentation Access](#api-documentation-access)
9. [Keyboard Shortcuts and Tips](#keyboard-shortcuts-and-tips)
10. [Roles and Permissions Quick Reference](#roles-and-permissions-quick-reference)

---

## Logging In

### First-Time Setup (Bootstrap)

The very first time the portal starts, there are no admin accounts yet. An
initial administrator must be created through the bootstrap process:

1. Open your browser and navigate to the portal address (for example
   `http://<your-server>:8080/admin`).
2. You will be prompted to create the first admin account by providing a
   **username**, **password**, and **email address**.
3. Once created, the bootstrap endpoint is permanently disabled — no one can
   use it again.

> **Important:** Choose a strong password. The system stores it using Argon2
> hashing, one of the most secure password algorithms available.

### Regular Login

1. Navigate to the admin interface (for example
   `http://<your-server>:8080/admin`).
2. You will see a login form with two fields: **Username** and **Password**.
3. Enter your credentials and click **Log In**.
4. On success you are taken directly to the [Dashboard](#dashboard-overview).

**What happens behind the scenes:**

- A secure session cookie is set in your browser. It is marked *HttpOnly*
  (invisible to scripts), *Secure* (sent only over HTTPS in production), and
  *SameSite=Strict* (blocks cross-site request forgery).
- Your session has a **30-minute idle timeout** — if you walk away and come
  back after 30 minutes of inactivity you will need to log in again.
- There is also an **8-hour absolute timeout**, after which you must log in
  again regardless of activity.

**Locked out?** If you enter incorrect credentials, the system enforces rate
limiting (5 attempts per 60 seconds by default). Wait a minute and try again.

### Logging Out

Click the **Logout** button in the top navigation bar at any time. Your session
is immediately destroyed and the session cookie is cleared.

---

## Dashboard Overview

After logging in you land on the **Dashboard** — your at-a-glance summary of
everything happening on the network.

**URL:** `/admin/dashboard`

### What You See

The dashboard is divided into two main sections:

#### Stat Cards

Four cards across the top of the page give you quick counts:

| Card | What It Shows |
|------|---------------|
| **Active Grants** | Number of guests currently connected to the network |
| **Pending Grants** | Grants that are scheduled but have not started yet |
| **Available Vouchers** | Voucher codes that have not been redeemed |
| **Integrations** | Number of Home Assistant integrations configured |

Each card is color-coded so you can spot issues at a glance.

#### Recent Activity

Below the stat cards is a table showing the latest actions taken in the system.
Each row includes:

- **Time** — when the action happened (in UTC)
- **Action** — what was done (for example "grant.revoke" or "voucher.create")
- **Target** — which item was affected (a grant ID, voucher code, etc.)
- **Admin** — who performed the action

This is a quick view into the full [Audit Log](#audit-log-access-and-filtering).

### Navigation Bar

A persistent navigation bar appears at the top of every page:

| Link | Destination |
|------|-------------|
| **Dashboard** | The summary page you are on now |
| **Grants** | [Grant Management](#grant-management) |
| **Vouchers** | [Voucher Generation and Management](#voucher-generation-and-management) |
| **Integrations** | [Entity Mapping](#entity-mapping-integrations) |
| **Settings** | [Configuration Management](#configuration-management) |
| **Logout** | Ends your session and returns to the login page |

---

## Grant Management

A **grant** is a time-limited permission that allows a specific device to use
the guest Wi-Fi network. Grants are the core of the captive portal — every
connected guest has one.

**URL:** `/admin/grants`

### Viewing Grants

When you open the Grants page you see a table of all grants in the system.
Each row shows:

| Column | Description |
|--------|-------------|
| **MAC Address** | The unique hardware address of the guest's device (for example `AA:BB:CC:DD:EE:FF`) |
| **Status** | Current state — see the color-coded badges below |
| **Booking Ref** | The booking reference associated with this grant (if any) |
| **Voucher** | The voucher code that was redeemed to create this grant (if any) |
| **Integration** | Which Home Assistant integration created or manages this grant |
| **Start** | When the grant begins (UTC) |
| **End** | When the grant expires (UTC) |
| **Grace Period** | Extra minutes of access allowed after checkout |
| **Actions** | Buttons to extend or revoke the grant |

#### Status Badges

| Badge | Color | Meaning |
|-------|-------|---------|
| **Pending** | Yellow | The grant exists but the start time has not arrived yet |
| **Active** | Green | The guest is currently authorized on the network |
| **Expired** | Red | The grant's end time has passed and access has ended |
| **Revoked** | Gray | An admin manually ended access before the grant expired |

#### Filtering Grants

At the top of the grants table is a **Filter** dropdown. Select one of:

- **All** — show every grant regardless of status
- **Pending** — only upcoming grants
- **Active** — only currently connected guests
- **Expired** — only grants that have ended naturally
- **Revoked** — only grants that were manually revoked

This makes it easy to, for example, see only the guests who are connected right
now.

### Extending a Grant

Sometimes a guest needs a little more time — maybe their flight is delayed or
checkout is pushed back. To extend a grant:

1. Find the grant in the table.
2. In the **Actions** column, enter the number of additional minutes in the
   input field (from **1** to **10,080** — that is up to 7 days).
3. Click the **Extend** button.
4. The **End** time updates immediately and the grant remains active for the
   extra duration.

> **Example:** A guest's grant expires at 11:00 AM but checkout was extended to
> 1:00 PM. Enter **120** minutes and click Extend.

Every extension is recorded in the [Audit Log](#audit-log-access-and-filtering).

### Revoking a Grant

If a guest's access needs to be terminated immediately — for example, a
no-show or a policy violation:

1. Find the grant in the table.
2. Click the **Revoke** button in the **Actions** column.
3. A confirmation prompt appears. Confirm to proceed.
4. The grant status changes to **Revoked** (gray badge) and the guest loses
   network access immediately.

> **Warning:** Revoking a grant is permanent. The grant cannot be reactivated.
> If the guest needs access again, create a new voucher or grant.

---

## Voucher Generation and Management

**Vouchers** are alphanumeric codes that guests enter on the captive portal
splash page to gain Wi-Fi access. Think of them like single-use access cards.

### Creating a Voucher

To generate a new voucher:

1. Navigate to the **Vouchers** page from the top menu.
2. Fill in the voucher creation form:

| Field | Required | Description | Range |
|-------|----------|-------------|-------|
| **Duration (minutes)** | Yes | How long the voucher grants access | 1 – 43,200 (up to 30 days) |
| **Booking Reference** | No | A label to tie the voucher to a reservation (for example "BOOKING-12345") | Up to 128 characters |
| **Upload Speed (kbps)** | No | Optional upload bandwidth limit for the guest | Any positive number |
| **Download Speed (kbps)** | No | Optional download bandwidth limit for the guest | Any positive number |
| **Code Length** | No | Number of characters in the generated code (default 10) | 4 – 24 characters |

3. Click **Create Voucher**.
4. The system generates a random uppercase alphanumeric code (letters A–Z and
   digits 0–9 only). For example: `A7K3MX9BPL`.
5. Share this code with your guest — they will enter it on the Wi-Fi splash
   page to connect.

> **Tip:** For short stays, a duration of **1440** minutes equals exactly
> **1 day**. For a weekend stay, use **4320** (3 days).

### Voucher Lifecycle

| Status | Meaning |
|--------|---------|
| **Unused** | The voucher has been created but no guest has redeemed it yet |
| **Active** | A guest has redeemed the code and is using it |
| **Expired** | The voucher's duration has elapsed |
| **Revoked** | An admin manually invalidated the voucher |

### How Guests Redeem Vouchers

When a guest connects to the Wi-Fi network, their browser is redirected to the
captive portal splash page. They enter the voucher code on this page, and the
system:

1. Validates the code.
2. Creates a time-limited access grant for the guest's device.
3. Redirects the guest to the internet (or a welcome page).

---

## Entity Mapping (Integrations)

The **Integrations** page lets you connect the captive portal to your Home
Assistant Rental Control integrations. This is how the system knows about your
property bookings so it can automatically grant Wi-Fi access to guests with
valid reservations.

**URL:** `/admin/integrations`

### What You See

The page is divided into two sections:

- **Left side:** A form to add or edit an integration.
- **Right side:** A table listing all configured integrations.

The table columns are:

| Column | Description |
|--------|-------------|
| **Integration ID** | The identifier matching your Home Assistant Rental Control integration (for example `rental_control_1`) |
| **Auth Attribute** | Which piece of booking data the guest uses to authenticate (see below) |
| **Grace Period** | How many extra minutes of Wi-Fi access a guest keeps after checkout |
| **Actions** | Edit or Delete buttons |

### Adding an Integration

1. In the form on the left side of the page, fill in:

| Field | Description | Default |
|-------|-------------|---------|
| **Integration ID** | Must exactly match the integration ID in Home Assistant (for example `rental_control_1`) | — |
| **Authorization Attribute** | Choose from the dropdown: **Slot Code** (a 4+ digit code), **Slot Name** (the guest's name), or **Last Four** (last 4 digits of an identifier) | Slot Code |
| **Checkout Grace Period** | Minutes of continued access after checkout (0–30) | 15 |

2. Click **Save**.
3. The integration appears in the table on the right.

### Editing an Integration

1. Click the **Edit** button next to the integration you want to change.
2. The form on the left populates with the current values.
3. Make your changes and click **Save**.

### Deleting an Integration

1. Click the **Delete** button next to the integration.
2. Confirm the deletion when prompted.

> **Note:** Deleting an integration does not immediately disconnect existing
> guests. Their active grants remain valid until they expire. However, no new
> automatic grants will be created for that integration's bookings.

### Authorization Attributes Explained

When a guest arrives and connects to Wi-Fi, they need to prove they have a
valid booking. The **Authorization Attribute** setting controls what the guest
enters on the splash page:

| Attribute | What the Guest Enters | Best For |
|-----------|-----------------------|----------|
| **Slot Code** | A numeric code (4+ digits) from their booking confirmation | Properties that email confirmation codes |
| **Slot Name** | Their name as it appears on the booking | Properties that verify by guest name |
| **Last Four** | The last 4 digits of a phone number or ID | Quick verification without sharing full details |

---

## Configuration Management

The **Settings** page lets you adjust portal-wide behavior without touching any
configuration files.

**URL:** `/admin/portal-settings`

### Rate Limiting

These settings protect the portal from brute-force attacks (someone trying to
guess voucher codes or credentials repeatedly):

| Setting | Description | Default | Range |
|---------|-------------|---------|-------|
| **Max Attempts** | Maximum number of authentication attempts allowed from a single IP address within the time window | 5 | 1 – 1,000 |
| **Time Window (seconds)** | The period over which attempts are counted — after this window resets, the counter starts over | 60 | 1 – 3,600 |

> **Example:** With the defaults, a guest (or attacker) can try 5 times in
> 60 seconds. After 5 failures they must wait for the window to reset before
> trying again.

### Redirect Behavior

These settings control what happens after a guest successfully authenticates:

| Setting | Description | Default |
|---------|-------------|---------|
| **Redirect to Original URL** | When checked, after authentication the guest is sent to the website they were originally trying to visit. When unchecked, they go to the success page instead. | Checked (on) |
| **Success Redirect URL** | The URL of the success/welcome page shown when "Redirect to Original URL" is unchecked | `/guest/welcome` |

> **Tip for property managers:** If you have a custom welcome page with house
> rules, local restaurant recommendations, or Wi-Fi tips, set the Success
> Redirect URL to that page and uncheck "Redirect to Original URL."

### Saving Changes

1. Adjust the settings as needed.
2. Click **Save Settings**.
3. Changes take effect immediately — no restart is required.

To undo unsaved changes, click **Reset** to restore the form to its current
saved values.

---

## Audit Log Access and Filtering

Every important action in the system is recorded in an immutable audit log.
This is your paper trail for security reviews, troubleshooting guest issues, or
answering "who did what and when?"

### What Gets Logged

| Event | Example |
|-------|---------|
| **Admin login** (success and failure) | "admin logged in" or "failed login attempt from 192.168.1.50" |
| **Voucher created** | "Voucher A7K3MX9BPL created with 1440-minute duration" |
| **Grant extended** | "Grant for AA:BB:CC:DD:EE:FF extended by 120 minutes" |
| **Grant revoked** | "Grant for AA:BB:CC:DD:EE:FF revoked" |
| **Portal configuration changed** | "Rate limit updated to 10 attempts per 120 seconds" |
| **Integration created, updated, or deleted** | "Integration rental_control_1 created" |
| **Permission denied** | "User 'viewer1' denied access to grants.revoke" |

### Audit Log Fields

Each log entry contains:

| Field | Description |
|-------|-------------|
| **Timestamp** | When the action happened (UTC) |
| **Actor** | The username or system process that performed the action |
| **Role** | The actor's role at the time (admin, operator, auditor, viewer) |
| **Action** | What was done (for example `grant.revoke` or `admin.login`) |
| **Target Type** | The kind of item affected (grant, voucher, session, config) |
| **Target ID** | The specific item's identifier (UUID, voucher code, etc.) |
| **Outcome** | Whether the action succeeded, failed, or was denied |
| **Metadata** | Additional details in JSON format (IP address, reason, etc.) |

### Viewing and Filtering Logs

The audit log is accessible through the admin interface. You can:

- **Filter by action type** — for example, show only "grant.revoke" events to
  see which grants were manually terminated.
- **Filter by actor** — see all actions performed by a specific admin.
- **Filter by outcome** — focus on failures or denied actions to investigate
  potential security issues.
- **Filter by date range** — narrow down to a specific time period.

### Audit Retention

By default, audit logs are retained for **30 days**. Administrators can adjust
the retention period (1–90 days) through the audit configuration API:

- `GET /api/admin/audit/config` — view current retention settings
- `PUT /api/admin/audit/config` — update retention period

> **Important:** Audit log entries are **immutable** — once recorded they cannot
> be edited or deleted (except by the automatic retention cleanup). This ensures
> a trustworthy record for compliance purposes.

---

## API Documentation Access

The captive portal includes built-in, interactive API documentation. This is
useful for advanced users, developers, or if you want to automate tasks using
scripts.

### Swagger UI

**URL:** `/admin/docs`

Swagger UI provides an interactive page where you can:

- Browse every API endpoint grouped by category.
- See the exact request format (which fields are required, their types, and
  allowed values).
- See example responses.
- **Try endpoints live** — fill in parameters and click "Execute" to send a
  real request directly from your browser.

This is the best starting point if you want to explore what the API can do.

### ReDoc

**URL:** `/admin/redoc`

ReDoc presents the same API information in a clean, readable, three-panel
layout:

- Left panel: navigation menu of all endpoints.
- Center panel: detailed documentation for the selected endpoint.
- Right panel: request and response examples.

ReDoc is ideal for reading and reference — it is easier to browse than Swagger
when you want to understand the API without running live requests.

> **Note:** Both documentation pages require admin authentication. You must be
> logged in to access them.

---

## Keyboard Shortcuts and Tips

### Browser Tips

Since the admin interface is a standard web application, your browser's built-in
shortcuts all work:

| Shortcut | Action |
|----------|--------|
| **Ctrl + R** (or **Cmd + R** on Mac) | Refresh the current page to see updated data |
| **Ctrl + F** (or **Cmd + F** on Mac) | Search for text on the current page — handy for finding a specific MAC address or voucher code in a long list |
| **Tab** | Move between form fields (useful when creating vouchers quickly) |
| **Shift + Tab** | Move to the previous form field |
| **Enter** | Submit the currently focused form |
| **Alt + Left Arrow** | Go back to the previous page |

### Productivity Tips

- **Bookmark the Dashboard.** Set `/admin/dashboard` as a browser bookmark for
  quick access.
- **Use the filter dropdown on Grants.** Instead of scrolling through hundreds
  of entries, filter to "Active" to see only current guests.
- **Copy voucher codes carefully.** Codes are uppercase letters and numbers
  only (A–Z, 0–9). There are no lowercase letters, so `0` (zero) and `O`
  (letter O) are the only pair to watch for.
- **Check recent activity first.** The dashboard's recent activity section is
  the fastest way to verify that an action you just took (like revoking a
  grant) actually happened.
- **Use browser tabs.** Open Grants in one tab and Vouchers in another to work
  with both at the same time.
- **Set a grace period on integrations.** A 15-minute grace period ensures
  guests are not cut off mid-checkout. Increase it if your checkout process
  takes longer.

---

## Roles and Permissions Quick Reference

Not every admin account has the same level of access. The system uses four
roles, from most restricted to most powerful:

| Role | Can View Grants | Can Manage Grants | Can Create Vouchers | Can View Audit Logs | Can Manage Settings | Can Manage Admin Accounts |
|------|:-:|:-:|:-:|:-:|:-:|:-:|
| **Viewer** | — | — | — | — | — | — |
| **Auditor** | ✅ | — | — | ✅ | — | — |
| **Operator** | ✅ | ✅ | ✅ | — | — | — |
| **Admin** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

- **Viewer** — read-only access to system health. Suitable for monitoring
  dashboards.
- **Auditor** — can view grants and audit logs but cannot make changes. Ideal
  for security or compliance review.
- **Operator** — the day-to-day role for property managers. Can create vouchers,
  extend or revoke grants, and manage guest access.
- **Admin** — full access to everything, including creating other admin
  accounts, changing portal settings, and managing integrations.

> For the complete permissions matrix, see
> [Permissions Matrix](permissions_matrix.md).

---

## Getting Help

- **Architecture and design:** [Architecture Overview](architecture_overview.md)
- **Initial setup:** [Quickstart Guide](quickstart.md)
- **Home Assistant integration:** [HA Integration Guide](ha_integration_guide.md)
- **TP-Link Omada setup:** [TP-Link Omada Setup](tp_omada_setup.md)
- **Permissions detail:** [Permissions Matrix](permissions_matrix.md)
- **API reference:** Log in and visit [`/admin/docs`](#swagger-ui) for
  interactive documentation
