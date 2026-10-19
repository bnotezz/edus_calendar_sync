# Security & Secret Protection Rules

## 1. Absolute Prohibition: No Remote Uploads
- **NEVER** run `git push`, `gh repo sync`, or upload files to remote servers unless explicitly instructed and authorized by the user.
- Commits must stay **strictly local**.

## 2. Secret Hygiene & Zero-Leak Policy
- **NEVER** hardcode or commit:
  - Google Cloud service account JSON keys or private keys (`-----BEGIN PRIVATE KEY-----`).
  - School portal tokens (JWT Bearer tokens `eyJ...`, refresh tokens).
  - School portal login credentials (usernames, emails, passwords).
  - GitHub Personal Access Tokens (`ghp_...`, `github_pat_...`).
  - Telegram bot tokens (`[0-9]{9,10}:[a-zA-Z0-9_-]{35}`).
  - Healthchecks.io ping UUIDs.
- Always use environment variables or local ignored files:
  - Configuration template: `.env.example` (tracked in git, safe placeholder values only).
  - Local configuration: `.env.local` or `.env` (strictly ignored by `.gitignore`).

## 3. Pre-Commit Secret Scanning
Before staging or committing any file, verify:
- No real credentials exist in modified files.
- `.env.local` and sensitive files are not staged (`git status` must not list them under changes to be committed).
- Ensure `.gitignore` continues to cover `.env`, `.env.*`, `keepalive.txt`, and log files.

## 4. GitHub Actions CI Security
- In CI workflows, ensure sensitive outputs use `::add-mask::<value>` before being emitted.
- All secrets must be passed via GitHub Secrets, never logged to stdout/stderr.
- Principle of least privilege: GitHub PATs must only have `Secrets: Read & Write` scope for this specific repository.
