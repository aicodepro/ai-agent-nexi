# CI workflows — one step to activate

These are the real, complete GitHub Actions workflows. They live here instead
of `.github/workflows/` for one reason only:

```
! [remote rejected] refusing to allow an OAuth App to create or update
  workflow `.github/workflows/ci-headless.yml` without `workflow` scope
```

GitHub blocks tokens without the `workflow` scope from pushing anything under
`.github/workflows/`. That is a credential-scope restriction, not a problem
with these files.

## Activate

From the repository root, with your own credentials:

```bash
mkdir -p .github/workflows
git mv ci/workflows/*.yml .github/workflows/
git commit -m "ci: activate headless, Windows and security lanes"
git push
```

Then watch the **Actions** tab. The first run is the evidence that the
repository is genuinely reproducible on a clean checkout — until it goes green,
"reproducible" is an assertion, not a fact.

## What each lane proves

| Workflow | Proves |
| --- | --- |
| `ci-headless.yml` | A clean Ubuntu checkout installs `.[test]`, compiles, collects tests, and passes the non-hardware suite. Also detects **undeclared first-party modules** — the exact defect class that a bad `.gitignore` glob caused before. |
| `ci-windows.yml` | The Windows lane installs `.[windows,browser,vision,test]`, installs Chromium, and runs everything except `-m audio` (runners have no microphone; that is not faked). |
| `security.yml` | Secret + personal-data scan (blocking on the working tree, informational on history until it is cleaned), gitleaks, `pip-audit`, CodeQL. |

## Expected initial results — read before trusting green

- The headless lane may need dependency adjustments on first run. It has
  **never executed on GitHub**; it was verified only by running its individual
  checks locally.
- `security.yml` history scanning is `continue-on-error: true` on purpose:
  history still contains known exposures needing owner-authorized rewriting
  (`security/history-rewrite-plan.md`). Make it blocking once history is clean.
- Markers (`windows`, `audio`, `browser`, `integration`) are **declared** in
  `pytest.ini` but not yet applied per test, so the headless filter currently
  excludes fewer tests than intended. Expect to tag tests as the lane reports
  failures.
