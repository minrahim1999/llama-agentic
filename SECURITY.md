# Security Policy

## Supported Releases

The latest tagged release on `main` is the only supported release line for security fixes.

## Reporting a Vulnerability

Please do not open a public issue for a suspected vulnerability.

Report security issues privately to the maintainer first. Include:

- affected version or commit SHA
- impact summary
- reproduction steps or proof of concept
- any suggested remediation

If the issue involves leaked credentials, rotate them immediately before reporting.

## Repository Hardening

This repository includes several protections in code and CI:

- `CODEOWNERS` coverage for the full repository, with explicit sensitive-path ownership
- pinned GitHub Actions commits for CI and publishing workflows
- CodeQL analysis for Python
- dependency review on pull requests
- secret scanning with Gitleaks
- publish-time verification that the pushed tag matches the package version in `pyproject.toml`

## Required GitHub Settings

These protections are only effective if the repository settings are also configured:

1. Protect `main` with pull requests only.
2. Require at least 2 approvals.
3. Require review from Code Owners.
4. Dismiss stale approvals when new commits are pushed.
5. Require all security and CI status checks to pass before merge.
6. Restrict who can push to `main`.
7. Create a tag ruleset so only trusted maintainers can create `v*` tags.
8. Require signed commits and signed tags for maintainers.
9. Keep PyPI on Trusted Publishing only; do not distribute PyPI API tokens to collaborators.

## Threat Model Notes

This project intentionally includes powerful local-automation features such as shell execution, background processes, plugin loading, and optional boot-time autostart. Those features are part of the product and are not hidden behavior, but they raise the risk of malicious changes if repository and release protections are weak.

Treat changes to the following areas as high risk:

- `.github/workflows/`
- `agent/tools/`
- `agent/plugins.py`
- `agent/mcp_client.py`
- `agent/a2a_client.py`
- `agent/autostart.py`
- `agent/server_manager.py`
- `pyproject.toml`
