# Nexi Supervised Agent Runtime

Nexi Studio is the supervisor and evidence authority. Governed Studio providers must enforce read-only stages and exact role tool policies; all agent runtimes remain unable to authorize gates, approve releases, or certify their own work.

## Runtime hierarchy

```text
Darsh (CEO)
  -> Nexi manager and Python supervisor
    -> selected primary agent runtime
      -> trusted specialist roles when that runtime supports delegation
    -> independent Nexi verification
      -> workspace diff
      -> tests
      -> QA
      -> security
      -> integration
      -> truthful local release state
```

Built-in providers:

| Provider | Adapter | Sessions | Events | Studio eligible | Important limitation |
| --- | --- | --- | --- | --- | --- |
| `claude-code` | Existing hardened Claude CLI adapter | Native | Structured JSON | Yes | Configuration isolation is not an OS sandbox |
| `opencode` | `opencode run --format json` | Native | Structured JSON | Yes | CLI cancellation is forced process termination |
| `hermes` | `hermes -z` | Fresh attempts | Final text | No | CLI permissions are prompt-only; use the Runs API in future |
| `openclaw` | `openclaw agent --json` | Session key | Terminal JSON | No | CLI permissions are prompt-only and Gateway may fall back |
| `antigravity` | Official Google Antigravity Python SDK worker | Fresh attempts | Text stream | No | Exact role tool policies are not yet enforced |
| `custom-cli` | Operator-supplied JSON argv | Declared | JSON/plain | No by default | Requires explicit conformance-tested capability declarations |

MCP supplies tools and context to agents; it is not used as a fake universal lifecycle protocol. ACP is the preferred future coding-agent protocol and A2A is the preferred future remote peer-agent protocol. Neither is claimed as implemented here.

## Configure Claude Code

```powershell
$env:NEXI_AGENT_RUNTIME_PROVIDER = "claude-code"
$env:NEXI_CLAUDE_CODE_ENABLED = "1"
$env:NEXI_STUDIO_ENABLED = "1"
$env:NEXI_STUDIO_ALLOW_HOST_EXECUTION = "1"
claude --version
```

Probe without running an agent:

```powershell
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider claude-code
```

Run a real disposable write-and-verify test:

```powershell
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider claude-code --live
```

A passing report requires all four:

- `agent_ok: true`
- `nexi_verified_on_track: true`
- `expected_file_content_matched: true`
- `exact_workspace_change_matched: true`

The project is created under the Windows temporary directory and removed afterward. Add `--keep` to inspect it.

## Configure OpenCode

```powershell
$env:NEXI_AGENT_RUNTIME_PROVIDER = "opencode"
$env:NEXI_AGENT_RUNTIME_ENABLED = "1"
$env:NEXI_OPENCODE_MODEL = "google/gemini-2.5-flash" # choose an authenticated model from `opencode models`
opencode --version
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider opencode --live
```

Nexi supplies an isolated OpenCode home and configuration, filters organization-discovery auth entries, disables project/external-skill/Claude compatibility configuration, disables plugins and MCP, and injects the SHA-verified role roster. The minimum authentication records needed by OpenCode are copied into the isolated process home and deleted after execution. Set `NEXI_OPENCODE_MODEL` explicitly so the isolated run does not depend on a global last-used model.

## Configure Hermes Agent

```powershell
$env:NEXI_AGENT_RUNTIME_PROVIDER = "hermes"
$env:NEXI_AGENT_RUNTIME_ENABLED = "1"
hermes --version
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider hermes --live
```

The CLI adapter runs in the authorized project directory because Hermes CLI does not document a per-request project root. Nexi snapshots and verifies the workspace, but this is not an OS sandbox. Hermes can run disposable supervised smoke tasks, but Studio rejects it because prompt-only permissions cannot guarantee read-only stages.

## Configure OpenClaw

Create or select an OpenClaw agent first, then:

```powershell
$env:NEXI_AGENT_RUNTIME_PROVIDER = "openclaw"
$env:NEXI_AGENT_RUNTIME_ENABLED = "1"
$env:NEXI_OPENCLAW_AGENT_ID = "main"
openclaw --version
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider openclaw --live
```

Nexi fails the run if OpenClaw reports embedded fallback. Set `NEXI_OPENCLAW_ALLOW_EMBEDDED_FALLBACK=1` only if that degraded mode is acceptable. OpenClaw is not Studio-eligible until its adapter enforces role permissions outside the prompt.

## Configure Google Antigravity

```powershell
.venv\Scripts\python.exe -m pip install google-antigravity
$env:NEXI_AGENT_RUNTIME_PROVIDER = "antigravity"
$env:NEXI_AGENT_RUNTIME_ENABLED = "1"
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider antigravity --live
```

The adapter opts into `CapabilitiesConfig()` only for writable supervised tasks. Read-only tasks retain the SDK's read-only default. Nexi still performs independent workspace and test verification. Antigravity is not Studio-eligible until exact role tool policies are enforced. This adapter creates an Antigravity SDK agent; it does not automate an already-running Antigravity desktop IDE.

## Connect another CLI agent

The custom adapter never invokes a shell. Configure a JSON argument array:

```powershell
$env:NEXI_AGENT_RUNTIME_PROVIDER = "custom-cli"
$env:NEXI_AGENT_RUNTIME_ENABLED = "1"
$env:NEXI_CUSTOM_AGENT_COMMAND_JSON = '["my-agent","run","--json","--cwd","{project_dir}","{prompt}"]'
.venv\Scripts\python.exe scripts\agent_runtime_smoke.py --provider custom-cli --live
```

Supported placeholders are `{prompt}`, `{project_dir}`, `{control_cwd}`, `{session_id}`, `{agent}`, and `{owner_id}`.
Custom capabilities default to false. Set the `NEXI_CUSTOM_AGENT_*` capability flags only after execution-level conformance tests prove those behaviors.

## Test the complete Studio flow

After a Studio-eligible provider smoke test passes, use an allowed disposable project and start Nexi normally:

```text
Nexi, start building a tiny local notes CLI with tests
```

Observe with:

```text
agent runtime status
studio status
```

The Eel bridge exposes runtime status only. Direct JavaScript start/stop calls are fail-closed; build and cancellation actions must pass through Nexi Studio's fresh, one-use authorization commands.

Expected behavior:

1. Nexi stores the selected provider and capabilities in `run.json`.
2. The primary agent receives the exact authorized target and SHA-verified role roster.
3. Safe reversible implementation-detail questions are answered by Nexi and audited as `manager_decisions`.
4. Scope, credentials, money, production, legal, personal-data, release, and irreversible questions are escalated to the CEO.
5. Every write stage is independently checked by workspace evidence and tests.
6. Read-only or test mutations block continuation until the workspace is restored.
7. The run ends at `LOCAL_VERIFIED` or `COMMITTED_LOCAL`; it does not claim deployment.

Run automated regression tests:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_agent_runtime.py tests/test_studio_supervisor.py tests/test_claude_code_dispatcher.py tests/test_claude_code_session.py -v
.venv\Scripts\python.exe -m pytest tests/test_nexi_agency_workflows.py -v
.venv\Scripts\python.exe -m compileall engine
.venv\Scripts\python.exe scripts\verify_safety.py
```

The optional loopback Agency HTTP server is not started by Nexi. If you start it manually, set a strong `NEXI_AGENCY_API_TOKEN` and send it as `Authorization: Bearer <token>`. Non-loopback binds and requests over 1 MiB are rejected.

## Research basis

Verified against official documentation on 2026-07-14:

- Claude Agent SDK and headless mode: <https://code.claude.com/docs/en/headless.md>
- OpenCode CLI/server/config: <https://opencode.ai/docs/cli/> and <https://opencode.ai/docs/server/>
- Hermes Runs API: <https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server>
- OpenClaw external apps and CLI: <https://docs.openclaw.ai/gateway/external-apps.md> and <https://docs.openclaw.ai/cli/agent.md>
- Google Antigravity platform and SDK: <https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/> and <https://pypi.org/project/google-antigravity/>
- ACP: <https://agentclientprotocol.com/overview/introduction>
- A2A: <https://a2a-protocol.org/latest/specification/>
