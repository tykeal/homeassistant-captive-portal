// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

/**
 * Progressive enhancement for grants management page.
 *
 * This script is OPTIONAL — all forms work without JavaScript via
 * standard HTML POST submissions. When loaded, it adds:
 *
 * - Confirmation dialogs before revoke actions
 * - Visual feedback during form submission
 *
 * CSP: This file MUST be loaded as an external script (script-src 'self').
 * No inline event handlers or inline scripts are used.
 */

(function () {
    "use strict";

    /**
     * Add confirmation dialog to revoke buttons.
     */
    function enhanceRevokeButtons() {
        var revokeForms = document.querySelectorAll(
            'form[action*="/admin/grants/revoke/"]'
        );
        revokeForms.forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (!window.confirm("Are you sure you want to revoke this grant?")) {
                    event.preventDefault();
                }
            });
        });
    }

    /**
     * Add loading state to submit buttons on form submission.
     */
    function enhanceSubmitButtons() {
        var forms = document.querySelectorAll("form[method='POST']");
        forms.forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (event.defaultPrevented) {
                    return;
                }
                var buttons = form.querySelectorAll('button[type="submit"]');
                buttons.forEach(function (button) {
                    if (!button.disabled) {
                        button.disabled = true;
                        button.textContent = button.textContent.trim() + "…";
                    }
                });
            });
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            enhanceRevokeButtons();
            enhanceSubmitButtons();
        });
    } else {
        enhanceRevokeButtons();
        enhanceSubmitButtons();
    }
})();
