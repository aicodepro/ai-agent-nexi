"""Direct brain-chain smoke test.

Loads .env, runs ask_brain("what is 2+2"), prints which provider answered
without leaking cookies or auth headers. Exit non-zero only on a code
crash, never on a provider failure.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()


def _safe_preview(text, limit=160):
    if text is None:
        return "(none)"
    s = str(text).strip()
    if len(s) > limit:
        s = s[:limit] + "..."
    return s


def main():
    try:
        from engine import features
    except Exception as e:
        print(f"[SMOKE] import failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1

    prompt = "what is 2+2"
    print(f"[SMOKE] prompt={prompt!r}")

    chain = features._resolve_provider_chain()
    print(f"[SMOKE] resolved chain={chain}")

    providers_tried = []
    fallback_used = False
    original_funcs = {}

    def make_wrapper(name, fn):
        def wrapped(prompt_):
            providers_tried.append(name)
            return fn(prompt_)
        return wrapped

    for name, fn in list(features._PROVIDER_FUNCS.items()):
        original_funcs[name] = fn
        features._PROVIDER_FUNCS[name] = make_wrapper(name, fn)

    try:
        try:
            answer = features.ask_brain(prompt)
        except Exception as e:
            print(f"[SMOKE] ask_brain crashed: {type(e).__name__}: {e}")
            traceback.print_exc()
            return 1
    finally:
        for name, fn in original_funcs.items():
            features._PROVIDER_FUNCS[name] = fn

    if len(providers_tried) > 1:
        fallback_used = True

    print(f"[SMOKE] providers_tried={providers_tried}")
    print(f"[SMOKE] fallback_used={'yes' if fallback_used else 'no'}")
    print(f"[SMOKE] answer_preview={_safe_preview(answer)!r}")

    # Sanity: never leak auth bits.
    auth = os.getenv("LIGHTNING_AUTH_BASE64", "")
    if auth and auth in (answer or ""):
        print("[SMOKE] WARNING: auth value appeared in answer; suppressing.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
