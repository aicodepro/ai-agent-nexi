"""Isolated process entry point for the optional Google Antigravity SDK."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--write", action="store_true")
    return parser


async def _run(prompt: str, writable: bool) -> int:
    try:
        from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
    except ImportError:
        print(json.dumps({"type": "error", "message": "google-antigravity is not installed."}))
        return 2
    options = {
        "system_instructions": (
            "You are an execution worker supervised by Nexi. Work only in the current authorized project. "
            "Do not claim success without tool evidence and do not perform release or deployment actions."
        )
    }
    if writable:
        options["capabilities"] = CapabilitiesConfig()
    config = LocalAgentConfig(**options)
    try:
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            chunks: list[str] = []
            async for token in response:
                text = str(token)
                chunks.append(text)
                print(json.dumps({"type": "text_delta", "text": text}, ensure_ascii=False), flush=True)
            final = "".join(chunks).strip()
            if not final:
                final = str(await response.text()).strip()
            print(json.dumps({"type": "result", "result": final}, ensure_ascii=False), flush=True)
            return 0
    except Exception as exc:
        print(json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 1


def main() -> int:
    args = _parser().parse_args()
    return asyncio.run(_run(args.prompt, args.write))


if __name__ == "__main__":
    raise SystemExit(main())
