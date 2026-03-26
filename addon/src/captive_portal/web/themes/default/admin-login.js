// SPDX-FileCopyrightText: 2025 Andrew Grimberg
// SPDX-License-Identifier: Apache-2.0

const rootPath = document.querySelector('meta[name="root-path"]').content;
const loginForm = document.getElementById('login-form');
const setupForm = document.getElementById('setup-form');
const cardTitle = document.getElementById('card-title');
const errorDiv = document.getElementById('login-error');

function showError(msg) {
    errorDiv.textContent = msg;
    errorDiv.style.display = 'block';
}

function hideError() {
    errorDiv.style.display = 'none';
}

// Check auth status and show appropriate form
async function checkAuthStatus() {
    try {
        const resp = await fetch(rootPath + '/api/admin/auth/status');
        const data = await resp.json();
        if (data.needs_setup) {
            cardTitle.textContent = 'Create Admin Account';
            loginForm.style.display = 'none';
            setupForm.style.display = 'block';
            document.getElementById('setup-username').focus();
        }
    } catch (_) {
        // Fall through to login form on error
    }
}

// Login form handler
loginForm.addEventListener('submit', async function(e) {
    e.preventDefault();
    hideError();

    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;

    try {
        const resp = await fetch(rootPath + '/api/admin/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password}),
        });

        if (resp.ok) {
            window.location.href = rootPath + '/admin/portal-settings/';
        } else {
            const data = await resp.json();
            showError(data.detail || 'Invalid username or password');
        }
    } catch (err) {
        showError('Unable to connect. Please try again.');
    }
});

// Setup form handler
setupForm.addEventListener('submit', async function(e) {
    e.preventDefault();
    hideError();

    const username = document.getElementById('setup-username').value;
    const email = document.getElementById('setup-email').value;
    const password = document.getElementById('setup-password').value;
    const confirm = document.getElementById('setup-confirm').value;

    if (password !== confirm) {
        showError('Passwords do not match.');
        return;
    }

    try {
        // Bootstrap the admin account
        const bootstrapResp = await fetch(rootPath + '/api/admin/auth/bootstrap', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password, email}),
        });

        if (!bootstrapResp.ok) {
            const data = await bootstrapResp.json();
            showError(data.detail || 'Failed to create admin account.');
            return;
        }

        // Auto-login with the new credentials
        const loginResp = await fetch(rootPath + '/api/admin/auth/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username, password}),
        });

        if (loginResp.ok) {
            window.location.href = rootPath + '/admin/portal-settings/';
        } else {
            // Bootstrap succeeded but login failed — redirect to login form
            window.location.reload();
        }
    } catch (err) {
        showError('Unable to connect. Please try again.');
    }
});

checkAuthStatus();
