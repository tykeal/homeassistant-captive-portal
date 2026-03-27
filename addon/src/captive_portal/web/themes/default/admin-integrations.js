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

        var manualInput = document.getElementById("integration_id_manual");
        var submitBtn = form.querySelector('button[type="submit"]');
        if (!submitBtn) {
            return;
        }

        function updateSubmitState() {
            // If manual input has a value, it takes priority
            if (manualInput && manualInput.value.trim()) {
                submitBtn.disabled = false;
                return;
            }
            var selectedOption = select.options[select.selectedIndex];
            if (selectedOption && selectedOption.disabled) {
                submitBtn.disabled = true;
            } else if (selectedOption && selectedOption.value === "") {
                submitBtn.disabled = true;
            } else {
                submitBtn.disabled = false;
            }
        }

        // When manual input is typed, copy value into the select's hidden field
        if (manualInput) {
            manualInput.addEventListener("input", function () {
                var val = manualInput.value.trim();
                if (val) {
                    // Override the dropdown: set select to blank and use manual value
                    select.value = "";
                    select.name = "";
                    select.required = false;
                    manualInput.name = "integration_id";
                    manualInput.required = true;
                } else {
                    // Revert: dropdown is the source
                    select.name = "integration_id";
                    select.required = true;
                    manualInput.name = "integration_id_manual";
                    manualInput.required = false;
                }
                updateSubmitState();
            });

            // When dropdown changes, clear manual input
            select.addEventListener("change", function () {
                if (select.value) {
                    manualInput.value = "";
                    select.name = "integration_id";
                    select.required = true;
                    manualInput.name = "integration_id_manual";
                    manualInput.required = false;
                }
                updateSubmitState();
            });
        } else {
            select.addEventListener("change", updateSubmitState);
        }

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

    /**
     * Enhance refresh button to fetch fresh discovery data via AJAX
     * and update the dropdown in-place without a full page reload.
     */
    function enhanceRefreshButton() {
        var refreshBtn = document.getElementById("refresh-discovery");
        if (!refreshBtn) {
            return;
        }

        refreshBtn.addEventListener("click", function () {
            refreshBtn.disabled = true;
            refreshBtn.textContent = "Refreshing…";
            refreshBtn.classList.add("refreshing");

            var discoverUrl = refreshBtn.getAttribute("data-discover-url") || "/api/integrations/discover";

            fetch(discoverUrl, {
                method: "GET",
                headers: { "Accept": "application/json" },
                credentials: "same-origin"
            })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Discovery request failed: " + response.status);
                }
                return response.json();
            })
            .then(function (data) {
                var select = document.getElementById("integration_id");
                if (!select || select.tagName.toLowerCase() !== "select") {
                    window.location.reload();
                    return;
                }

                var currentValue = select.value;

                // Clear existing options except placeholder
                while (select.options.length > 1) {
                    select.remove(1);
                }

                // Populate with fresh data
                var integrations = data.integrations || [];
                integrations.forEach(function (disc) {
                    var option = document.createElement("option");
                    option.value = disc.entity_id;
                    var label = disc.friendly_name + " (" + disc.entity_id + ")";
                    if (disc.already_configured) {
                        label += " (already added)";
                        option.disabled = true;
                    }
                    if (disc.state_display) {
                        label += " — " + disc.state_display;
                    }
                    if (disc.event_summary) {
                        label += " | " + disc.event_summary;
                    }
                    option.textContent = label;
                    select.appendChild(option);
                });

                // Restore selection if still available
                if (currentValue) {
                    select.value = currentValue;
                    if (!select.value) {
                        select.selectedIndex = 0;
                    }
                }

                enhanceIntegrationDropdown();

                refreshBtn.textContent = "Refresh Discovery";
                refreshBtn.disabled = false;
                refreshBtn.classList.remove("refreshing");
            })
            .catch(function () {
                window.location.reload();
            });
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            enhanceIntegrationDropdown();
            enhanceDeleteButtons();
            enhanceSubmitButtons();
            enhanceRefreshButton();
        });
    } else {
        enhanceIntegrationDropdown();
        enhanceDeleteButtons();
        enhanceSubmitButtons();
        enhanceRefreshButton();
    }
})();
