// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

// Client-side validation
document.getElementById('portal-config-form').addEventListener('submit', function(e) {
    const attempts = parseInt(document.getElementById('rate_limit_attempts').value, 10);
    const windowSeconds = parseInt(
        document.getElementById('rate_limit_window_seconds').value, 10
    );

    if (attempts < 1 || attempts > 1000) {
        e.preventDefault();
        alert('Rate limit attempts must be between 1 and 1000');
        return false;
    }

    if (windowSeconds < 1 || windowSeconds > 3600) {
        e.preventDefault();
        alert('Rate limit window must be between 1 and 3600 seconds');
        return false;
    }
});
