// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

/**
 * Progressive enhancement for integrations management page.
 *
 * This script is OPTIONAL — all forms work without JavaScript via
 * standard HTML POST submissions. When loaded, it adds:
 *
 * - Disables submit when an "(already added)" option is selected
 * - Confirmation dialogs before delete actions
 * - Visual feedback during form submission
 *
 * CSP: This file MUST be loaded as an external script (script-src 'self').
 * No inline event handlers or inline scripts are used.
 */

(function () {
    "use strict";

    /**
     * Disable submit button when a disabled/already-configured option
     * is selected in the integration_id dropdown.
     */
    function enhanceIntegrationDropdown() {
        var select = document.getElementById("integration_id");
        if (!select || select.tagName.toLowerCase() !== "select") {
            return;
        }

        var form = select.closest("form");
        if (!form) {
            return;
        }

        var submitBtn = form.querySelector('button[type="submit"]');
        if (!submitBtn) {
            return;
        }

        function updateSubmitState() {
            var selectedOption = select.options[select.selectedIndex];
            if (selectedOption && selectedOption.disabled) {
                submitBtn.disabled = true;
            } else if (selectedOption && selectedOption.value === "") {
                submitBtn.disabled = true;
            } else {
                submitBtn.disabled = false;
            }
        }

        select.addEventListener("change", updateSubmitState);
        updateSubmitState();
    }

    /**
     * Add confirmation dialog to delete buttons.
     */
    function enhanceDeleteButtons() {
        var deleteForms = document.querySelectorAll(
            'form[action*="/admin/integrations/delete/"]'
        );
        deleteForms.forEach(function (form) {
            form.addEventListener("submit", function (event) {
                if (!window.confirm("Are you sure you want to delete this integration?")) {
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
            enhanceIntegrationDropdown();
            enhanceDeleteButtons();
            enhanceSubmitButtons();
        });
    } else {
        enhanceIntegrationDropdown();
        enhanceDeleteButtons();
        enhanceSubmitButtons();
    }
})();
