---
name: security-scanner
description: Audits project files, git status, and commits for leaked secrets, API keys, private keys, and unmasked credentials.
---

# Security Scanner Skill

Use this skill whenever code or configuration files are modified, before making any git commit.

## When to Run
- After modifying files that handle credentials, tokens, or environment variables.
- Before staging files with `git add`.
- During security reviews or audits.

## Verification Checklist
1. **Inspect Git Status**:
   ```bash
   git status
   ```
   Ensure `.env.local`, `.env`, credentials files, and temporary logs are NOT in "Changes to be committed" or "Untracked files".

2. **Regex Secret Scan**:
   Scan tracked files for sensitive patterns:
   - Google Service Account keys: `-----BEGIN PRIVATE KEY-----`
   - JWT tokens: `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`
   - GitHub PAT: `ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}`
   - Telegram Bot Tokens: `[0-9]{9,10}:[a-zA-Z0-9_-]{35}`
   - Passwords in code: `password\s*=\s*['"][^'"]+['"]`

3. **Check .gitignore Integrity**:
   Verify `.gitignore` rules prevent leaking secrets:
   ```bash
   git check-ignore -v .env .env.local keepalive.txt output.log
   ```
