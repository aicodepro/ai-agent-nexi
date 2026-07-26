# Credential Rotation Checklist

**Status:** `BLOCKED_EXTERNAL_SECURITY_AUTHORIZATION`
**Why blocked:** rotation requires authenticated access to the provider
consoles. An agent must not rotate credentials on the owner's behalf.

Secret values are never printed in this repository. Credentials are referenced
by provider and by a SHA-256 fingerprint prefix recorded in
`security/secret-inventory.json`.

---

## Why this is urgent

Both credentials were committed to a **public** repository
(`github.com/aicodepro/ai-agnet-nexi`). Automated scrapers harvest public
GitHub commits continuously. Assume both keys are compromised, regardless of
whether abuse has been observed yet.

The current working tree is clean. **Git history is not.** Removing a file in a
later commit does not remove it from earlier commits.

---

## SEC-001 — Google / Gemini API key

- **Provider:** Google AI Studio / Google Cloud
- **Pattern:** `AIza…` (39 chars)
- **Was located in:** `archive/audit.md` (quoted as evidence by an earlier audit)
- **Current tree:** redacted
- **History:** still present
- **Live status at last check:** not verified in this session

**Steps**

1. Sign in to <https://console.cloud.google.com/apis/credentials> (or Google AI Studio).
2. Locate the API key beginning `AIza…`. Match against the fingerprint in the inventory.
3. **Create a replacement key first**, so the assistant keeps working.
4. Apply restrictions to the new key: API restriction = Generative Language API; add an application restriction if practical.
5. Put the new value in the local `.env` as `GEMINI_API_KEY=` (never commit `.env`; it is gitignored).
6. Verify Nexi still answers a question (brain path).
7. **Delete the old key.**
8. Review usage/billing for unexpected activity while it was public.
9. Record completion in `security/secret-inventory.json` (`remediation_state`).

## SEC-002 — Groq API key

- **Provider:** Groq Cloud
- **Pattern:** `gsk_…` (56 chars)
- **Was located in:** `archive/audit.md`
- **Current tree:** redacted
- **History:** still present
- **Live status:** **CONFIRMED LIVE** — during this session, `/chat/completions`
  and `/models` both returned HTTP 200. This key works right now.

**Steps**

1. Sign in to <https://console.groq.com/keys>.
2. Create a replacement key.
3. Put it in the local `.env` as `GROQ_API_KEY=`.
4. Verify: wake-word → speech → ASR still transcribes (Groq Whisper), and intent routing still resolves.
5. **Revoke the old key.**
6. Check usage for anomalies.
7. Record completion in the inventory.

---

## After rotation

- [ ] Both old keys revoked at the provider
- [ ] New keys present only in the local, gitignored `.env`
- [ ] `python scripts/verify_repository_sanitization.py` → clean working tree
- [ ] Decide on history: see `security/history-rewrite-plan.md`
- [ ] Enable GitHub secret-scanning **push protection** (repo → Settings → Code security)
- [ ] `security/secret-inventory.json` updated to `rotated`

## Do not

- Do not paste real key values into issues, reports, chat logs or commits.
- Do not assume redacting the current file fixed the exposure.
- Do not mark this remediated until the provider shows the old keys revoked.
