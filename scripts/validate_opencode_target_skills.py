"""Validate OpenCode target skills: folder existence, SKILL.md, frontmatter, required sections, and forbidden strings."""
import os
import re
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SKILLS_DIR = os.path.join(REPO_ROOT, ".opencode", "skills")

TARGET_SKILLS = [
    "skill-create-skill",
    "mcp-builder",
    "browser-agent",
    "web-design-guidelines",
    "frontend-design",
]

REQUIRED_SECTIONS = [
    "# Purpose",
    "# When to Use",
    "# Inputs",
    "# Workflow",
    "# Output Format",
    "# Safety Rules",
    "# Do Not Do",
    "# Verification Checklist",
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


def extract_frontmatter_field(text, field):
    match = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def has_forbidden_strings(text, patterns):
    text_lower = text.lower()
    for label, pattern, case_sensitive in patterns:
        if case_sensitive:
            if re.search(pattern, text):
                return label
        else:
            if re.search(pattern, text, re.IGNORECASE):
                return label
    return None


FORBIDDEN_PATTERNS = [
    ("hardcoded API key (sk-)", r"sk-[A-Za-z0-9]{10,}", True),
    ("hardcoded API key (api_key=)", r"api_key\s*=\s*['\"][A-Za-z0-9_\-]{10,}", False),
    ("hardcoded API key (API_KEY=)", r"API_KEY\s*=\s*['\"][A-Za-z0-9_\-]{10,}", True),
    ("curl | bash instruction", r"curl\s+\S+\s*\|\s*(bash|sh)", False),
    ("curl | sh instruction", r"curl\s+\S+\s*\|\s*sh", False),
    ("edit global config instruction", r"(edit|modify|change)\s+(global\s+)?config", False),
    ("enable MCP automatically instruction", r"(enable|activate|start)\s+MCP\s+(server\s+)?automatically", False),
]


def validate_skill(skill_name, required_sections, forbidden_patterns):
    skill_dir = os.path.join(SKILLS_DIR, skill_name)
    skill_md = os.path.join(skill_dir, "SKILL.md")

    check(f"[{skill_name}] Folder exists", os.path.exists(skill_dir),
          f"Missing folder: {skill_dir}")
    check(f"[{skill_name}] SKILL.md exists", os.path.exists(skill_md),
          f"Missing SKILL.md: {skill_md}")

    if not os.path.exists(skill_md):
        return

    with open(skill_md, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    check(f"[{skill_name}] YAML frontmatter exists", has_yaml_frontmatter(text),
          "SKILL.md must start with YAML frontmatter (---)")

    name_field = extract_frontmatter_field(text, "name")
    desc_field = extract_frontmatter_field(text, "description")
    check(f"[{skill_name}] frontmatter has name: field",
          name_field is not None, "Missing 'name:' in frontmatter")
    check(f"[{skill_name}] frontmatter has description: field",
          desc_field is not None, "Missing 'description:' in frontmatter")

    for section in required_sections:
        check(f"[{skill_name}] section '{section}' exists",
              section in text, f"Missing section: {section}")

    violation = has_forbidden_strings(text, forbidden_patterns)
    check(f"[{skill_name}] no forbidden strings",
          violation is None, f"Found: {violation}")


def main():
    global PASS, FAIL
    PASS = 0
    FAIL = 0
    print("=" * 60)
    print("OPENCODE TARGET SKILLS VALIDATION")
    print("=" * 60)

    print("\n[Target Skills Checks]")
    for skill in TARGET_SKILLS:
        validate_skill(skill, REQUIRED_SECTIONS, FORBIDDEN_PATTERNS)

    print("\n[Index & Router Checks]")
    index_path = os.path.join(SKILLS_DIR, "SKILL_INDEX.md")
    check("SKILL_INDEX.md exists", os.path.exists(index_path),
          f"Missing: {index_path}")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8", errors="replace") as f:
            index_text = f.read()
        for skill in TARGET_SKILLS:
            check(f"SKILL_INDEX.md references '{skill}'", skill in index_text,
                  f"Missing reference to {skill} in SKILL_INDEX.md")

    router_path = os.path.join(REPO_ROOT, "OPENCODE_TARGET_SKILL_ROUTER_GUIDE.md")
    check("OPENCODE_TARGET_SKILL_ROUTER_GUIDE.md exists",
          os.path.exists(router_path), f"Missing: {router_path}")

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
