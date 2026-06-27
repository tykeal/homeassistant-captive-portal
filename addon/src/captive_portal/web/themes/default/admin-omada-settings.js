// SPDX-FileCopyrightText: 2026 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

// Client-side validation for Omada settings form
document.addEventListener('DOMContentLoaded', function() {
    var form = document.getElementById('omada-config-form');
    var passwordField = document.getElementById('password');
    var passwordChanged = document.getElementById('password_changed');
    var clientSecretField = document.getElementById('client_secret');
    // aislop-ignore-next-line ai-slop/hardcoded-id -- DOM field id, not provider id
    var clientSecretChanged = document.getElementById('client_secret_changed');

    // Track password field changes
    if (passwordField && passwordChanged) {
        passwordField.addEventListener('input', function() {
            passwordChanged.value = 'true';
        });
    }
    if (clientSecretField && clientSecretChanged) {
        clientSecretField.addEventListener('input', function() {
            clientSecretChanged.value = 'true';
        });
    }

    if (form) {
        form.addEventListener('submit', function(e) {
            var controllerUrl = document.getElementById('controller_url').value.trim();
            var controllerId = document.getElementById('controller_id').value.trim();
            var openapiMode = document.getElementById('openapi_mode').value;

            // Validate controller URL format if non-empty
            if (controllerUrl) {
                try {
                    var url = new URL(controllerUrl);
                    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
                        e.preventDefault();
                        alert('Controller URL must use HTTP or HTTPS protocol.');
                        return false;
                    }
                } catch (err) {
                    e.preventDefault();
                    alert('Please enter a valid controller URL.');
                    return false;
                }
            }

            // Validate controller ID format if non-empty
            if (controllerId && !/^[a-fA-F0-9]{12,64}$/.test(controllerId)) {
                e.preventDefault();
                alert('Controller ID must be a hex string (12-64 characters).');
                return false;
            }
            if (['auto', 'openapi', 'legacy'].indexOf(openapiMode) === -1) {
                e.preventDefault();
                alert('Backend mode must be auto, openapi, or legacy.');
                return false;
            }
        });
    }
});
