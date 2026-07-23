"""Quick test script to verify MCP health check works."""
from engine.mcp_tool_bridge import check_mcp_health, validate_mcp_config, mcp_health_summary

print("=== MCP Health Check ===")
results = check_mcp_health()
for r in results:
    err = f"ERROR: {r.error}" if r.error else ""
    print(f"  {r.name:20s} ({r.source:6s}): cmd_ok={str(r.command_resolves):5s}, pkg={str(r.package_exists):5s}, auto={r.auto_start}, opt={r.is_optional} {err}")

print()
print("=== MCP Config Validation ===")
issues = validate_mcp_config()
for i in issues:
    print(f"  [{i['severity']:7s}] {i.get('source',''):30s} {i['message']}")
if not issues:
    print("  No issues found!")

print()
print("=== MCP Health Summary ===")
h = mcp_health_summary()
print(f"  Summary: {h['summary_line']}")
for s in h["servers"]:
    print(f"  {s['name']:20s}: {s['state']:20s} (source={s['source']})")
