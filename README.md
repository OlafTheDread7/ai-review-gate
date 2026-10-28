# AI Review gate

A GitHub Action that has Claude review every push to `main` for security and architecture problems, and holds the deploy until it passes. I run it on more than 30 of my own repos: static sites on Vercel, Flask and Node apps on Railway.

I push straight to `main` with no pull requests, so there was no review step anywhere. This puts one between the push and production. Vercel's Deployment Checks and Railway's "Wait for CI" won't ship a commit until this check is green.

## What runs on each push

1. **Scope.** `prepare.sh` works out what to review: everything since the last commit that passed. A blocked change stays in the diff until it's fixed, so pushing something unrelated on top doesn't sneak it through.
2. **Plain checks, no AI** (`checks.py`, a few seconds):
   - **Publish check.** Works out the host (static Vercel site, Vercel build, Railway or another server) and lists the files the deploy would serve. It flags review notes, Markdown, `docs/`, secret files, databases, exports and scripts that would go live.
   - **Secret scan.** gitleaks over the new commits, with an allow-list for keys that are public on purpose (Stripe publishable, form and captcha site keys).
   - **Dependency audit.** `npm audit` for lockfiles, and the OSV database for pinned Python packages.
3. **The AI review.** Claude Code reads the diff and the code around it, with read-only tools, against the rubric in `REVIEW.md`: injection, XSS, SSRF, auth, secrets, data integrity on money paths, and broken contracts. It returns findings as JSON with a severity, a file and line, and a fix.
4. **The verdict** (`enforce.py`). Critical or high from either side holds the deploy. So does a missing result: if the checks or the review don't report, nothing ships. Findings go to the job summary and as annotations on the files, and new critical, high and medium ones each open a GitHub issue.

Pushes that only touch images and fonts, or only the gate's own files, skip the AI review. The plain checks still run.

## Install

You need a Claude subscription token in the repo's secrets: run `claude setup-token`, then `gh secret set CLAUDE_CODE_OAUTH_TOKEN --repo <owner>/<repo>`. Set it before your first push with the gate, or that first run fails and holds the deploy.

`files/github/` mirrors a repo's `.github` folder. The installers copy it in and never touch your own `CONTEXT.md` or `surface.json` unless you pass them. Both preview first.

Windows (PowerShell):

```powershell
.\Install-AIReview.ps1 -Repo C:\code\my-site                 # preview
.\Install-AIReview.ps1 -Repo C:\code\my-site -Context .\notes\CONTEXT.md -Go
.\Install-AIReview.ps1 -All -Root C:\code -Go                # update every repo that has it
```

macOS or Linux:

```bash
bash install.sh path/to/my-site                               # preview
bash install.sh --go --context notes/CONTEXT.md path/to/my-site
```

Then commit the `.github` files, push, and turn on the deploy hold:

- **Vercel:** Project Settings, Deployment Checks, add "AI Review" for Production.
- **Railway:** the service's settings, turn on "Wait for CI".

## Per-repo files

- **`.github/ai-review/CONTEXT.md`**: notes for the reviewer. What the project is, its entry points, where money and customer data go, environment variable names, and what's public on purpose. There's an example in `examples/CONTEXT.md`. This is what keeps the review from flagging things you meant to do.
- **`.github/ai-review/surface.json`**: settings, all optional:

```json
{
  "host": "auto",
  "root": "",
  "output_dir": "",
  "static_dirs": ["static"],
  "publish": ["data/public-dataset.csv"],
  "issues": true
}
```

`host` overrides the detection (`vercel-static`, `vercel-output`, `vercel-build`, `railway`, `server`, `none`). `root` is the subfolder Vercel deploys from. `publish` lists files that are meant to go live. `"issues": false` stops the gate opening GitHub issues, which I use on public repos. On a public repo the run's job summary is public either way.

Every static site on Vercel should have a `.vercelignore` so notes and CI files don't get served. The one I use is in `examples/vercelignore`.

## Severity

| Severity | Holds the deploy | Opens an issue | Examples |
|---|---|---|---|
| critical | yes | yes | a live key in the repo, an auth bypass, a database file that would be served |
| high | yes | yes | XSS a visitor can reach, an unverified payment webhook, review notes that would go live |
| medium | no | yes | a weakness that needs an unusual condition, a dependency audit that couldn't reach its database |
| low | no | no | hardening worth doing eventually |

A dependency database that's down is reported as medium on purpose, so an outage somewhere else doesn't hold every deploy.

## Tests

```bash
python -m unittest discover -s tests -v
```

They build throwaway repos and run `checks.py`, `enforce.py` and `prepare.sh` against them the way the workflow does. Standard library only. Needs git and bash.

## Limits

- It reviews what changed since the last pass, not the whole codebase. Run the workflow by hand with `whole-repo` for a full audit.
- The publish check reads the repo, not the live site. Check the live site yourself after the first deploy (`/.github/ai-review/CONTEXT.md` should be a 404).
- Claude can miss things and can be wrong. It's a gate, not a guarantee.

## License

MIT. See `LICENSE`.
