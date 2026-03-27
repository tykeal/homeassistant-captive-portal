// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

/**
 * Progressive enhancement for voucher management page.
 * Select-all checkbox functionality. Forms work without JS.
 */

(function () {
    "use strict";

    var selectAll = document.getElementById("select-all");
    if (!selectAll) return;

    var checkboxes = document.querySelectorAll('input[name="codes"]');

    // Toggle all checkboxes when select-all changes
    selectAll.addEventListener("change", function () {
        for (var i = 0; i < checkboxes.length; i++) {
            checkboxes[i].checked = selectAll.checked;
        }
    });

    // Update select-all state when individual checkboxes change
    function updateSelectAll() {
        var total = checkboxes.length;
        var checked = 0;
        for (var i = 0; i < total; i++) {
            if (checkboxes[i].checked) checked++;
        }
        selectAll.checked = checked === total && total > 0;
        selectAll.indeterminate = checked > 0 && checked < total;
    }

    for (var i = 0; i < checkboxes.length; i++) {
        checkboxes[i].addEventListener("change", updateSelectAll);
    }
})();
