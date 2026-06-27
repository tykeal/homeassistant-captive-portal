# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Compatibility import for the legacy TP-Omada controller adapter."""

from captive_portal.controllers.tp_omada.legacy_adapter import OmadaLegacyAdapter

OmadaAdapter = OmadaLegacyAdapter

__all__ = ["OmadaAdapter", "OmadaLegacyAdapter"]
