# Development & Quality Assurance Workflow

## 1. Incremental Verification Cycle
After finishing work on any logical block of code, the agent MUST immediately execute the verification cycle:
1. **Lint & Code Style**:
   - Run `flake8` to ensure PEP-8 compliance:
     ```bash
     .venv/bin/flake8 sync.py tests --max-line-length=130
     ```
2. **Run Test Suite**:
   - Run all automated unit and integration tests:
     ```bash
     .venv/bin/pytest tests -v
     # or using standard library:
     python3 -m unittest discover tests
     ```
   - All tests must pass with 0 failures and 0 errors.
   - Maintain test coverage above 85%.

3. **Check Dependencies**:
   - Verify that installed dependencies are fresh, without outdated or vulnerable packages:
     ```bash
     .venv/bin/pip list --outdated
     ```
   - Keep `requirements.txt` and `requirements-dev.txt` synchronized.

4. **Security & Secret Leak Check**:
   - Check staged changes and modified files for secrets, tokens, or personal identifiers.
   - Confirm `.env.local` remains untracked.

5. **Documentation & Rule Updates**:
   - If features, options, or behavior changed, update `README.md`, `SECURITY.md`, and architecture docs accordingly.

6. **Local Git Commit**:
   - Stage relevant modified files.
   - Create a clean, descriptive Conventional Commit:
     - `feat: ...` for new features
     - `fix: ...` for bug fixes
     - `test: ...` for test additions/updates
     - `refactor: ...` for code refactoring
     - `docs: ...` for documentation
     - `chore: ...` for maintenance
   - **DO NOT RUN `git push`. DO NOT UPLOAD TO REMOTE REPOSITORIES.**
