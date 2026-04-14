// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

// Client-side validation
document.getElementById('portal-config-form').addEventListener('submit', function(e) {
    var attempts = parseInt(document.getElementById('rate_limit_attempts').value, 10);
    var windowSeconds = parseInt(
        document.getElementById('rate_limit_window_seconds').value, 10
    );
    var idleMinutes = parseInt(
        document.getElementById('session_idle_minutes').value, 10
    );
    var maxHours = parseInt(
        document.getElementById('session_max_hours').value, 10
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

    if (idleMinutes < 1 || idleMinutes > 1440) {
        e.preventDefault();
        alert('Session idle timeout must be between 1 and 1440 minutes');
        return false;
    }

    if (maxHours < 1 || maxHours > 168) {
        e.preventDefault();
        alert('Session max duration must be between 1 and 168 hours');
        return false;
    }
});
