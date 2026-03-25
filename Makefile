# SPDX-FileCopyrightText: 2025 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0

.PHONY: addon-prep addon-clean

## Stage source files into addon/ for HA Supervisor Docker build
addon-prep:
	cp pyproject.toml addon/pyproject.toml
	cp README.md addon/README.md
	rm -rf addon/src
	cp -r src addon/src

## Remove staged build artifacts from addon/
addon-clean:
	rm -f addon/pyproject.toml addon/README.md
	rm -rf addon/src
