import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()


def main():
    provider = os.getenv("NEXI_BRAIN_PROVIDER", "hugchat")
    print(f"[TEST] NEXI_BRAIN_PROVIDER={provider}")
    print(f"[TEST] LIGHTNING_API_BASE={os.getenv('LIGHTNING_API_BASE', '(not set)')}")
    print(f"[TEST] LIGHTNING_AUTH_SET={bool(os.getenv('LIGHTNING_AUTH_BASE64'))}")
    print(f"[TEST] LIGHTNING_AGENT_SET={bool(os.getenv('LIGHTNING_AGENT_ID'))}")

    if not os.getenv("LIGHTNING_AUTH_BASE64") or not os.getenv("LIGHTNING_AGENT_ID"):
        print("\n[TEST] Lightning not fully configured. Skipping live API call.")
        print("[TEST] Set LIGHTNING_AUTH_BASE64 and LIGHTNING_AGENT_ID in .env to run live test.")
        return

    from engine.lightning_gateway import ask_lightning

    prompt = "what is 2+2"
    print(f"\n[TEST] Sending: {prompt}")
    response = ask_lightning(prompt)
    print(f"[TEST] Response: {response}")


if __name__ == "__main__":
    main()
