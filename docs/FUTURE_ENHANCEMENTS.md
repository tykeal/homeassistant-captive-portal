<!--
SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Future Enhancements

This document tracks planned enhancements and improvements for future development.

## Internationalization (i18n) Support

**Priority**: Low
**Effort**: Medium
**Phase**: Post-MVP

### Description
All user-facing text is currently hardcoded in English. Add internationalization support to enable multi-language deployments for global rental properties.

### Affected Areas
- All HTML templates (`src/captive_portal/templates/`)
- User-facing error messages
- Email notifications (future feature)
- Admin UI text

### Implementation Considerations
- Use Flask-Babel or similar i18n framework
- Extract translatable strings to message catalogs
- Add language selection mechanism (browser detection + manual override)
- Consider right-to-left (RTL) language support
- Maintain English as default/fallback language

### Use Cases
- Rental properties in non-English-speaking countries
- International guest support
- Multi-property operators with global locations

---

## Metrics and Observability

**Priority**: Low
**Effort**: Medium
**Phase**: Post-MVP

### Description
Add comprehensive metrics instrumentation for monitoring, alerting, and performance analysis.

### Proposed Metrics
- Authorization success/failure rates
- Rate limit hit count (by endpoint, by IP)
- Authorization latency (p50, p95, p99)
- Active grants count
- Voucher creation/redemption rate
- Booking code validation success rate
- Controller API call latency and error rates

### Implementation Considerations
- Use Prometheus client library
- Add `/metrics` endpoint for Prometheus scraping
- Consider Grafana dashboard templates
- Add health check endpoint (`/health`)
- Log structured metrics for analysis

### Use Cases
- Detect system issues before users report them
- Capacity planning (peak guest arrival times)
- Performance optimization (identify slow operations)
- Security monitoring (unusual authorization patterns)

---

## Accessibility Improvements

**Priority**: Low
**Effort**: Medium
**Phase**: Post-MVP

### Description
Enhance HTML templates to meet WCAG 2.1 Level AA accessibility standards.

### Required Improvements
- Add ARIA labels to form inputs and buttons
- Use semantic HTML elements (`<nav>`, `<main>`, `<section>`)
- Ensure keyboard navigation works without mouse
- Add skip-to-content links
- Improve color contrast ratios
- Add screen reader testing
- Provide text alternatives for visual elements
- Ensure error messages are announced to screen readers

### Implementation Considerations
- Run automated accessibility audits (axe, Lighthouse)
- Manual testing with screen readers (NVDA, JAWS, VoiceOver)
- Consider mobile accessibility (touch targets, zoom)
- Document accessibility features for users

### Use Cases
- Users with visual impairments
- Users relying on keyboard navigation
- Compliance with accessibility regulations (ADA, Section 508)
- Improved usability for all users

---

## Progressive Enhancement

**Priority**: Low
**Effort**: Low
**Phase**: Post-MVP

### Description
Ensure guest portal forms work without JavaScript enabled, degrading gracefully.

### Current State
- Forms rely on JavaScript for optimal UX
- No-JS fallback is basic but may be incomplete
- Some features may not work without JavaScript

### Proposed Improvements
- Verify all forms submit correctly without JavaScript
- Add server-side validation feedback without AJAX
- Ensure redirect handling works without JavaScript
- Test with JavaScript disabled in various browsers
- Add `<noscript>` messages where appropriate
- Consider progressive enhancement for real-time features

### Implementation Considerations
- Test core authorization flow without JavaScript
- Ensure error messages display properly
- Validate that redirect URL preservation works
- Consider inline form validation fallbacks

### Use Cases
- Users with JavaScript disabled for security/privacy
- Users on restricted networks that block JavaScript
- Legacy browsers or assistive technologies
- Improved reliability (JavaScript loading failures)

---

## Related Documentation
- Phase 5 Code Review: `/home/tykeal/repos/personal/homeassistant/captive-portal/phase5_code_review.md`
- Guest Authorization Spec: `/home/tykeal/repos/personal/homeassistant/captive-portal/docs/guest_authorization.md`
