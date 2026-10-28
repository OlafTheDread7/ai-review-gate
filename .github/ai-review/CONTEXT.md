# ai-review-gate: notes for the reviewer

Public repo. The reusable AI Review ship gate: a GitHub Actions workflow plus the scripts it runs. Nothing here deploys.

- `files/github/` is the product: the workflow (`workflows/ai-review.yml`) and `ai-review/prepare.sh`, `checks.py`, `enforce.py`, `gitleaks.toml`, `REVIEW.md`. Users copy them into their own `.github/`. This repo's own `.github/` is an installed copy of the same files.
- `Install-AIReview.ps1` and `install.sh` copy those files into a local repo. They run no git and take paths from the person running them.
- `tests/test_gate.py` builds throwaway repos in a temp folder.

What matters most: anything in `files/github/` that could leak a token, run untrusted input as shell, widen the workflow's permissions, or let a held deploy through (the fail-closed paths in `enforce.py`). The workflow runs on pushes to main and manual dispatch only, never on pull requests from forks.

Public by design: `gitleaks.toml` lists key formats that are public on purpose (Stripe publishable, form and captcha site keys). The only secret is `CLAUDE_CODE_OAUTH_TOKEN`, referenced by name.
