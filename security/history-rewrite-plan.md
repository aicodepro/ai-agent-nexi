# Git History Rewrite Plan

**Status:** `BLOCKED_EXTERNAL_SECURITY_AUTHORIZATION`
**Why blocked:** rewriting and force-pushing shared public history is
destructive and irreversible for collaborators. It requires explicit owner
authorization. This plan is prepared, not executed.

---

## What is still in history

`git rm --cached` (already done) stops *future* distribution. It does not alter
past commits. Still retrievable from the public remote:

| Item | Path | Sensitivity |
| --- | --- | --- |
| Google/Gemini API key | `archive/audit.md` | credential |
| Groq API key (confirmed live) | `archive/audit.md` | credential |
| ~270 personal wake-word recordings | `hey_nexi_clips/*.wav` | biometric-adjacent (voice) |
| Recent ASR captures | `artifacts/last_asr_request.wav`, `last_empty_asr.wav` | private speech |
| LBPH face-recognition model (~17 MB) | `trainingData.yml` | **biometric** |
| Generated training audio | `datasets/**` | bulk data |
| Local databases | `jarvis.db`, `nexai.db`, `nexi.db` | possibly personal |

Voice and face data of an identifiable person carry obligations under GDPR
Art. 9 / UK GDPR (biometric and special-category data) if the person is
identifiable — which they are, since this is the owner's own data. This is a
stronger reason to clean history than the API keys alone.

---

## Decision first: rotate before rewriting

**Rotate the credentials first** (`credential-rotation-checklist.md`).

Once rotated, the keys in history become worthless, and the rewrite becomes a
*privacy* action about voice/biometric data rather than an emergency. Rewriting
without rotating leaves live keys in every existing clone and fork.

---

## Option A — Rewrite history (recommended if the repo must stay public)

Uses `git-filter-repo` (the tool the Git project recommends over
`filter-branch`).

```bash
# 0. Full backup first - this is destructive.
git clone --mirror https://github.com/aicodepro/ai-agnet-nexi.git nexi-backup.git
tar -czf nexi-backup-$(date +%Y%m%d).tar.gz nexi-backup.git

# 1. Fresh mirror to operate on
git clone --mirror https://github.com/aicodepro/ai-agnet-nexi.git nexi-clean.git
cd nexi-clean.git

# 2. Remove personal/biometric/bulk data from every commit
git filter-repo --invert-paths \
  --path hey_nexi_clips \
  --path datasets \
  --path artifacts \
  --path trainingData.yml \
  --path jarvis.db --path nexai.db --path nexi.db \
  --path ai-team-agents-v2.zip

# 3. Redact credential strings from every commit.
#    replacements.txt maps each literal secret to a placeholder.
#    Build it locally from .env / the provider console. NEVER commit it.
git filter-repo --replace-text ../replacements.txt

# 4. Verify BEFORE pushing
cd .. && git clone nexi-clean.git nexi-verify && cd nexi-verify
python scripts/verify_repository_sanitization.py --history   # must exit 0

# 5. Force-push (OWNER AUTHORIZATION REQUIRED)
cd ../nexi-clean.git
git push --force --mirror https://github.com/aicodepro/ai-agnet-nexi.git
```

`replacements.txt` format (build locally, never commit):

```
<old-google-key>==>REDACTED_GOOGLE_API_KEY
<old-groq-key>==>REDACTED_GROQ_API_KEY
```

### Consequences — read before authorizing

- **Every commit SHA after the earliest rewritten commit changes.**
- All clones and forks must re-clone; `git pull` will not reconcile.
- Open PRs against old SHAs break.
- GitHub may retain unreferenced objects; open a support request to purge
  cached views of the old commits.
- Forks are **not** rewritten. If the repo was ever forked, the data persists
  in the fork and only the fork owner can remove it.

## Option B — Fresh repository (simplest, safest)

If history has no external value:

1. Create a new empty repository.
2. Push only the current clean tree as a single initial commit.
3. Archive or make private the old repository.
4. Update remotes and CI.

Loses history; carries zero rewrite risk. Preferred when the repo is
single-author and the history is mostly this migration.

## Option C — Make the repository private

Fastest containment. Does **not** undo prior public exposure (assume already
scraped) and does not remove the data, but stops further access.

Still rotate the credentials.

---

## Verification (required for any option)

```bash
python scripts/verify_repository_sanitization.py --history --json
```

Must report `"clean": true`. Anything else means the rewrite missed a path or a
pattern. The script detects by vendor pattern, so it also catches secrets that
were never on the original inventory.

## Recommendation

1. **Rotate both keys now** (unblocked by anything, ~5 minutes).
2. Then choose **Option B** if history isn't valuable, else **Option A**.
3. Enable push protection so this cannot recur.
