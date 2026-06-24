"""Validate claude-flow-orchestration skill: folder, SKILL.md sections, security checks, index/router references, and design documents."""
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS_DIR = os.path.join(REPO_ROOT, ".opencode", "skills")
SKILL_NAME = "claude-flow-orchestration"

REQUIRED_SECTIONS = [
    "# Purpose",
    "# When to Use",
    "# Inputs",
    "# Workflow",
    "# Agent Roles",
    "# Swarm Plan Format",
    "# Safety Gates",
    "# Output Format",
    "# Verification Checklist",
    "# Do Not Do",
]

DESIGN_DOCS = [
    "OPENCODE_CLAUDE_FLOW_PLUGIN_DESIGN.md",
    "OPENCODE_CLAUDE_FLOW_MCP_DESIGN.md",
    "CLAUDE_FLOW_OPTIONAL_INSTALL_APPROVAL_PLAN.md",
]

FORBIDDEN_PATTERNS = [
    ("hardcoded API key", r"(?:sk\-[A-Za-z0-9]{10,}|api_key\s*=|API_KEY\s*=)", True),
    ("curl | bash instruction", r"curl\s+\S+\s*\|\s*bash", False),
    ("curl | sh instruction", r"curl\s+\S+\s*\|\s*sh", False),
    ("npx claude-flow without approval",
     r"npx\s+claude-flow\b(?!.*(?:approval|approve|ask|confirm|prompt|permission))", False),
    ("MCP auto-enable instruction",
     r"(enable|activate|start)\s+MCP\s+(server\s+)?automatically", False),
    ("global config edit instruction",
     r"(edit|modify|change)\s+(global\s+)?config", False),
    ("plugin auto-load instruction",
     r"(auto.?load|auto.?enable|auto.?activate)\s+plugin", False),
]

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS: {name}")
        PASS += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        FAIL += 1


def has_yaml_frontmatter(text):
    stripped = text.lstrip()
    return stripped.startswith("---")


def has_forbidden_strings(text, patterns):
    for label, pattern, case_sensitive in patterns:
        if case_sensitive:
            if re.search(pattern, text):
                return label
        else:
            if re.search(pattern, text, re.IGNORECASE):
                return label
    return None


def main():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    print("=" * 60)
    print("OPENCODE CLAUDE FLOW SKILL VALIDATION")
    print("=" * 60)

    print(f"\n[{SKILL_NAME} Checks]")
    skill_dir = os.path.join(SKILLS_DIR, SKILL_NAME)
    skill_md = os.path.join(skill_dir, "SKILL.md")

    check(f"Folder exists", os.path.exists(skill_dir),
          f"Missing folder: {skill_dir}")
    check(f"SKILL.md exists", os.path.exists(skill_md),
          f"Missing: {skill_md}")

    if not os.path.exists(skill_md):
        print("\nCannot continue without SKILL.md")
        print(f"\n{'=' * 60}")
        print(f"RESULTS: {PASS} passed, {FAIL} failed")
        print(f"{'=' * 60}")
        return 1

    with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    check(f"YAML frontmatter exists", has_yaml_frontmatter(text),
          "SKILL.md must start with YAML frontmatter (---)")

    for section in REQUIRED_SECTIONS:
        check(f"section '{section}' exists",
              section in text, f"Missing section: {section}")

    violation = has_forbidden_strings(text, FORBIDDEN_PATTERNS)
    check(f"no forbidden strings",
          violation is None, f"Found: {violation}")

    print("\n[Index & Router References]")
    index_path = os.path.join(SKILLS_DIR, "SKILL_INDEX.md")
    check(f"SKILL_INDEX.md exists", os.path.exists(index_path),
          f"Missing: {index_path}")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8", errors="replace") as f:
            index_text = f.read()
        check(f"SKILL_INDEX.md includes '{SKILL_NAME}'",
              SKILL_NAME in index_text,
              f"Missing reference to {SKILL_NAME} in SKILL_INDEX.md")

    router_path = os.path.join(REPO_ROOT, "OPENCODE_SKILL_ROUTER_GUIDE.md")
    check(f"OPENCODE_SKILL_ROUTER_GUIDE.md exists",
          os.path.exists(router_path), f"Missing: {router_path}")
    if os.path.exists(router_path):
        with open(router_path, "r", encoding="utf-8", errors="replace") as f:
            router_text = f.read()
        check(f"OPENCODE_SKILL_ROUTER_GUIDE.md includes '{SKILL_NAME}'",
              SKILL_NAME in router_text,
              f"Missing reference to {SKILL_NAME} in OPENCODE_SKILL_ROUTER_GUIDE.md")

    print("\n[Design Documents]")
    for doc_name in DESIGN_DOCS:
        doc_path = os.path.join(REPO_ROOT, doc_name)
        check(f"{doc_name} exists",
              os.path.exists(doc_path), f"Missing: {doc_path}")

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
