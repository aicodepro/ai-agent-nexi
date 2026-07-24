# Mark-L Licence And Reuse Notes

## Evidence

- Repository: `https://github.com/FatihMakes/Mark-L.git`.
- Local checkout audited on 2026-07-23.
- No standalone `LICENSE` file was present in the checkout.
- `readme.md` lines 159-162 state "Personal and non-commercial use only" and identify Creative Commons BY-NC 4.0.

## Consequence

CC BY-NC 4.0 is not an appropriate dependency licence for a potentially commercial assistant product without separate permission. The absence of a standalone licence file also increases ambiguity about source-code licensing scope.

## Enforced Reuse Rule

- Do not copy Mark-L code, prompts, UI assets, text, or configuration into Nexi.
- Do not add Mark-L as a package, submodule, vendored directory, or runtime dependency.
- Architectural ideas may be independently reimplemented from public behavior descriptions.
- Keep an audit trail of the concept adopted, Nexi-specific design, and independently written implementation.
- Obtain explicit written permission from the Mark-L copyright holder before any direct code or asset reuse.

## Current Status

No Mark-L source code has been copied into Nexi. The audit documents record patterns and rejection decisions only.
