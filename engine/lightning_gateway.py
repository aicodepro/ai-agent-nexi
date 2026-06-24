import json
import os
import time
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from dotenv import load_dotenv

load_dotenv()

DEFAULT_SYSTEM_PROMPT = (
    "You are Jarvis. Keep answers short, sharp, voice-friendly, and interruptible. "
    "Give concise answers unless the user asks for details."
)


def _load_config():
    api_base = os.getenv("LIGHTNING_API_BASE", "").rstrip("/")
    auth_b64 = os.getenv("LIGHTNING_AUTH_BASE64", "")
    project_id = os.getenv("LIGHTNING_BILLING_PROJECT_ID", "")
    agent_id = os.getenv("LIGHTNING_AGENT_ID", "")
    stream = os.getenv("LIGHTNING_STREAM", "true").lower() == "true"
    timeout = int(os.getenv("LIGHTNING_TIMEOUT_SECONDS", "90"))
    return api_base, auth_b64, project_id, agent_id, stream, timeout


def _check_config(api_base, auth_b64, agent_id):
    missing = []
    if not api_base:
        missing.append("LIGHTNING_API_BASE")
    if not auth_b64:
        missing.append("LIGHTNING_AUTH_BASE64")
    if not agent_id:
        missing.append("LIGHTNING_AGENT_ID")
    return missing


def _build_headers(auth_b64, project_id):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_b64}",
    }
    if project_id:
        headers["X-Project"] = project_id
    return headers


def _parse_stream_chunks(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    parts = []
    stopped = False
    for line in text.splitlines():
        if stopped:
            break
        line = line.strip()
        if not line:
            continue
        if line.startswith("data: "):
            line = line[6:]
        if line.startswith(":") or line.startswith("event:"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        choices = data.get("result", {}).get("choices", [])
        for choice in choices:
            delta = choice.get("delta", {})
            content = delta.get("content", "")
            if content:
                parts.append(content)
            finish = choice.get("finish_reason")
            if finish and finish != "null" and finish is not None:
                stopped = True
                break
    return "".join(parts)


def _parse_non_stream_body(body: bytes) -> str:
    try:
        data = json.loads(body.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return ""
    choices = data.get("choices", [])
    if not choices:
        return data.get("result", "")
    parts = []
    for c in choices:
        msg = c.get("message", {})
        content = msg.get("content", "")
        if content:
            parts.append(content)
    return "".join(parts)


def ask_lightning(prompt: str, system_prompt: str | None = None) -> str:
    api_base, auth_b64, project_id, agent_id, stream, timeout = _load_config()
    missing = _check_config(api_base, auth_b64, agent_id)
    if missing:
        print(f"[LIGHTNING] config missing: {', '.join(missing)}")
        return "Brain connection is not configured."

    print(f"[LIGHTNING] config api_base={api_base} auth_configured=True agent_configured=True")

    url = f"{api_base}/chat/completions"
    headers = _build_headers(auth_b64, project_id)
    sp = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT

    body = {
        "agent_id": agent_id,
        "messages": [
            {"role": "system", "content": sp},
            {"role": "user", "content": prompt},
        ],
        "stream": stream,
    }

    request = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    print(f"[LIGHTNING] request started")
    start = time.time()

    try:
        response = urlopen(request, timeout=timeout)
        status = response.status
        raw = response.read()
        elapsed = time.time() - start
        print(f"[LIGHTNING] status={status} elapsed={elapsed:.2f}s")

        if status != 200:
            return ""

        if stream:
            answer = _parse_stream_chunks(raw)
            print(f"[LIGHTNING] chunks=1 size={len(raw)}")
        else:
            answer = _parse_non_stream_body(raw)
            print(f"[LIGHTNING] response size={len(raw)}")

        return answer.strip()

    except HTTPError as e:
        print(f"[LIGHTNING] status={e.code} error={e.reason}")
        return ""
    except URLError as e:
        print(f"[LIGHTNING] connection error: {e.reason}")
        return ""
    except Exception as e:
        print(f"[LIGHTNING] error: {e}")
        return ""
