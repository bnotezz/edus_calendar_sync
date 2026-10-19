---
name: sync-verifier
description: Runs the full verification pipeline for Edus Calendar Sync including linting, unit tests, coverage reports, and dependency freshness.
---

# Sync Verifier Skill

Use this skill to run automated quality assurance checks on the Edus Calendar Sync project.

## Verification Commands

1. **Code Formatting & Linting**:
   ```bash
   .venv/bin/flake8 sync.py tests --max-line-length=130
   ```

2. **Automated Unit Tests**:
   ```bash
   .venv/bin/pytest tests -v
   # or with native unittest:
   python3 -m unittest discover tests -v
   ```

3. **Code Coverage Report**:
   ```bash
   .venv/bin/coverage run -m pytest tests
   .venv/bin/coverage report -m
   ```
   Target minimum: 85% coverage on `sync.py`.

4. **Dependency Freshness**:
   ```bash
   .venv/bin/pip list --outdated
   ```
   Ensure no required packages are deprecated or critically outdated.
