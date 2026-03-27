// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

/**
 * Progressive enhancement for voucher management page.
 *
 * This script is OPTIONAL — all forms work without JavaScript via
 * standard HTML POST submissions. When loaded, it adds:
 *
 * - Select-all / deselect-all checkbox toggling
 * - Bulk action button enable/disable based on selection
 * - Confirmation dialogs before destructive actions
 *
 * CSP: This file MUST be loaded as an external script (script-src 'self').
 * No inline event handlers or inline scripts are used.
 */

(function () {
    "use strict";

    /**
     * Wire up select-all checkbox and bulk-action button state.
     */
    function enhanceSelectAll() {
        var selectAll = document.getElementById("select-all");
        if (!selectAll) {
            return;
        }

        var tableBody = document.querySelector(
            "#bulk-form table.data-table tbody"
        );
        if (!tableBody) {
            return;
        }

        var checkboxes = Array.prototype.slice.call(
            tableBody.querySelectorAll('input[type="checkbox"]')
        );

        var bulkForm = document.getElementById("bulk-form");
        var bulkButtons = [];
        if (bulkForm) {
            bulkButtons = Array.prototype.slice.call(
                bulkForm.querySelectorAll(
                    '.bulk-action-bar button[type="submit"]'
                )
            );
        }

        function updateBulkButtons() {
            if (!bulkButtons.length) {
                return;
            }
            var anyChecked = checkboxes.some(function (cb) {
                return cb.checked;
            });
            bulkButtons.forEach(function (btn) {
                btn.disabled = !anyChecked;
            });
        }

        selectAll.addEventListener("change", function () {
            var checked = selectAll.checked;
            checkboxes.forEach(function (cb) {
                cb.checked = checked;
            });
            updateBulkButtons();
        });

        checkboxes.forEach(function (cb) {
            cb.addEventListener("change", function () {
                if (!cb.checked && selectAll.checked) {
                    selectAll.checked = false;
                } else if (
                    cb.checked &&
                    checkboxes.every(function (c) {
                        return c.checked;
                    })
                ) {
                    selectAll.checked = true;
                }
                updateBulkButtons();
            });
        });

        updateBulkButtons();
    }

    /**
     * Add confirmation dialogs to destructive single-voucher actions.
     */
    function enhanceDestructiveButtons() {
        var deleteButtons = document.querySelectorAll(
            'button[formaction*="/delete/"]'
        );
        deleteButtons.forEach(function (button) {
            button.addEventListener("click", function (event) {
                if (
                    !window.confirm(
                        "Are you sure you want to delete this voucher?"
                    )
                ) {
                    event.preventDefault();
                }
            });
        });

        var bulkDeleteBtn = document.querySelector(
            'button[formaction*="/bulk-delete"]'
        );
        if (bulkDeleteBtn) {
            bulkDeleteBtn.addEventListener("click", function (event) {
                if (
                    !window.confirm(
                        "Are you sure you want to delete all selected vouchers?"
                    )
                ) {
                    event.preventDefault();
                }
            });
        }
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
            enhanceSelectAll();
            enhanceDestructiveButtons();
            enhanceSubmitButtons();
        });
    } else {
        enhanceSelectAll();
        enhanceDestructiveButtons();
        enhanceSubmitButtons();
    }
})();
