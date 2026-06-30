import os
import sys
import re
import json
import argparse
import tempfile
import subprocess
from pathlib import Path

from skills_evaluation_dashboard import render_skills_evaluation_dashboard

SCRIPT_DIR = Path(__file__).parent.resolve()
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(Path(tempfile.gettempdir()) / "tiktoken-cache"))

import tiktoken

# ── CONFIG ────────────────────────────────────────────────────────────────────

CONFIG_PATHS = [
    SCRIPT_DIR / "skills_evaluation_tests.json",
    SCRIPT_DIR.parent / "tests" / "skills_evaluation_tests.json",
]

def load_config() -> dict:
    for config_path in CONFIG_PATHS:
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)

    searched = ", ".join(str(path) for path in CONFIG_PATHS)
    print(f"ERROR: skills_evaluation_tests.json not found. Checked: {searched}")
    sys.exit(1)

CONFIG = load_config()

# ── SECURITY PATTERNS ─────────────────────────────────────────────────────────
# Scans for hardcoded credentials based on gitleaks and detect-secrets patterns.

SECURITY_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API Key"),
    (r'ghp_[a-zA-Z0-9]{36,}', "GitHub PAT"),
    (r'gho_[a-zA-Z0-9]{36,}', "GitHub OAuth Token"),
    (r'AIza[0-9A-Za-z\-_]{35}', "Google API Key"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key"),
    (r'[Aa][Pp][Ii][_-]?[Kk][Ee][Yy]\s*[=:]\s*["\'][^"\']{10,}["\']', "Generic API Key"),
    (r'[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]\s*[=:]\s*["\'][^"\']{5,}["\']', "Hardcoded Password"),
    (r'[Tt][Oo][Kk][Ee][Nn]\s*[=:]\s*["\'][^"\']{10,}["\']', "Hardcoded Token"),
    (r'[Ss][Ee][Cc][Rr][Ee][Tt]\s*[=:]\s*["\'][^"\']{5,}["\']', "Hardcoded Secret"),
    (r'-----BEGIN (RSA|EC|OPENSSH|PGP) PRIVATE KEY', "Private Key"),
    (r'Bearer [a-zA-Z0-9\-_\.]{20,}', "Bearer Token"),
    (r'[Cc]onnection[Ss]tring\s*[=:]\s*["\'][^"\']{10,}["\']', "Connection String"),
]

def check_security(content: str):
    found = [label for pattern, label in SECURITY_PATTERNS if re.search(pattern, content)]
    return len(found) == 0, found

# ── FRONTMATTER PARSER ────────────────────────────────────────────────────────
# Extracts key-value pairs from the YAML --- block at the top of SKILL.md.

def parse_frontmatter(content: str):
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not match:
        return False, {}
    fm_data = {}
    current_key = None
    current_value = []
    for line in match.group(1).split('\n'):
        if ':' in line and not line.startswith(' '):
            if current_key:
                fm_data[current_key] = ' '.join(current_value).strip().strip("'\"")
            parts = line.split(':', 1)
            current_key = parts[0].strip()
            current_value = [parts[1].strip()] if len(parts) > 1 else []
        elif current_key and line.startswith(' '):
            current_value.append(line.strip())
    if current_key:
        fm_data[current_key] = ' '.join(current_value).strip().strip("'\"")
    return True, fm_data

# ── TIER HELPERS ──────────────────────────────────────────────────────────────

def pct_to_tier(pct: float, good_min: float, avg_min: float) -> str:
    if pct >= good_min:
        return "STRONG"
    if pct >= avg_min:
        return "MODERATE"
    return "WEAK"

def tier_to_score(tier: str) -> int:
    return {"STRONG": 3, "MODERATE": 2, "WEAK": 1}[tier]

def weighted_avg(scores: dict, weights: dict) -> float:
    return sum(scores[k] * weights[k] for k in scores)

def avg_to_pct(avg: float) -> float:
    return round(((avg - 1) / 2) * 100, 1)

# ── STRUCTURE CHECKS ──────────────────────────────────────────────────────────
# Validates file format, filename, YAML frontmatter, required fields,
# field constraints, body size, headings, line limits, paths, and URLs.

def run_structure_checks(skill_file, name, content, has_frontmatter,
                         has_name, has_desc, desc_text, name_text, char_count):
    cfg_s = CONFIG["structure"]
    lines = content.splitlines()
    return {
        "file_is_markdown": skill_file.suffix == ".md",
        "filename_kebab_case": bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name)),
        "yaml_frontmatter_exists": has_frontmatter,
        "required_fields_present": has_name and has_desc,
        "field_length_valid": (
            0 < len(desc_text) <= cfg_s["max_description_chars"] and
            0 < len(name_text) <= cfg_s["max_name_chars"]
        ),
        "body_size_valid": cfg_s["min_body_chars"] <= char_count <= cfg_s["max_body_chars"],
        "has_headings": bool(re.search(r'^#{1,3} .+', content, re.MULTILINE)),
        "under_line_limit": len(lines) <= cfg_s["hard_line_limit"],
        "within_optimal_lines": len(lines) <= cfg_s["optimal_line_limit"],
        "no_absolute_paths": not bool(re.search(r'[A-Za-z]:\\|^/[a-z]+/', content, re.MULTILINE)),
        "no_external_urls": not bool(re.search(r'https?://', content)),
    }

# ── CONTENT QUALITY CHECKS ────────────────────────────────────────────────────
# Validates when-to-use, instructions, examples, sections, tags,
# code block leaks, placeholder text, meaningful length,
# section dominance, duplicate phrases, and bullet length.

def run_quality_checks(content, char_count):
    cfg_cq = CONFIG["content_quality"]
    forbidden_blocks = ["```python", "```json", "```yaml", "```javascript", "```bash"]

    section_matches = re.findall(r'\n## .{1,80}\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    section_content = " ".join(section_matches)
    section_ratio = len(section_content) / char_count if char_count > 0 else 0

    words = content.lower().split()
    phrase_len = cfg_cq["duplicate_phrase_words"]
    min_repeats = cfg_cq["duplicate_phrase_min"]
    phrases = [" ".join(words[i:i+phrase_len]) for i in range(len(words) - phrase_len + 1)]
    phrase_counts = {p: phrases.count(p) for p in set(phrases)}
    has_duplicates = any(v >= min_repeats for v in phrase_counts.values())

    bullets = re.findall(r'^\s*[-*]\s+(.+)', content, re.MULTILINE)
    bullets_ok = all(len(b.split()) <= cfg_cq["bullet_word_limit"] for b in bullets) if bullets else True

    return {
        "has_when_to_use": bool(re.search(r'##?\s*(when to use|trigger|use case)', content, re.IGNORECASE)),
        "has_instructions": bool(re.search(r'##?\s*(instruction|workflow|step|how to|usage)', content, re.IGNORECASE)),
        "has_examples": bool(re.search(r'##?\s*(example|sample)', content, re.IGNORECASE)),
        "has_multiple_sections": content.count('## ') >= 2,
        "no_code_block_leaks": not any(b in content for b in forbidden_blocks),
        "has_structured_tags": bool(re.search(r'<[a-zA-Z][^>]{0,50}>', content)),
        "no_placeholder_text": not bool(re.search(r'\[TODO\]|\[PLACEHOLDER\]|\[INSERT\]', content, re.IGNORECASE)),
        "has_meaningful_length": char_count > 200,
        "section_dominance_met": section_ratio >= cfg_cq["section_dominance_pct"],
        "no_duplicate_phrases": not has_duplicates,
        "bullets_within_limit": bullets_ok,
    }

# ── TOKEN EFFICIENCY CHECK ────────────────────────────────────────────────────
# Counts exact tokens using tiktoken cl100k_base encoding.

def run_token_check(content):
    cfg_tok = CONFIG["token_thresholds"]
    enc = tiktoken.get_encoding("cl100k_base")
    token_count = len(enc.encode(content))
    if token_count <= cfg_tok["strong_max"]:
        tier = "STRONG"
    elif token_count <= cfg_tok["moderate_max"]:
        tier = "MODERATE"
    else:
        tier = "WEAK"
    return tier, token_count

# ── BENCHMARK ─────────────────────────────────────────────────────────────────

def benchmark_skill(folder_path: Path) -> dict:
    skill_file = folder_path / "SKILL.md"
    if not skill_file.exists():
        return None
    try:
        content = skill_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return {"name": folder_path.name, "error": "Invalid UTF-8", "overall": "WEAK (0.0%)"}

    name = folder_path.name
    char_count = len(content)
    line_count = len(content.splitlines())
    cfg_cq = CONFIG["content_quality"]

    has_frontmatter, fm = parse_frontmatter(content)
    has_name = bool(fm.get("name", "").strip())
    has_desc = bool(fm.get("description", "").strip())
    desc_text = fm.get("description", "")
    name_text = fm.get("name", "")

    structure_checks = run_structure_checks(
        skill_file, name, content,
        has_frontmatter, has_name, has_desc,
        desc_text, name_text, char_count
    )
    struct_pct = round(sum(structure_checks.values()) / len(structure_checks) * 100, 1)
    struct_tier = pct_to_tier(struct_pct, 85, 50)

    quality_checks = run_quality_checks(content, char_count)
    quality_pct = round(sum(quality_checks.values()) / len(quality_checks) * 100, 1)
    quality_tier = pct_to_tier(quality_pct, cfg_cq["good_min_pct"], cfg_cq["average_min_pct"])

    token_tier, token_count = run_token_check(content)

    security_ok, found_secrets = check_security(content)
    security_tier = "STRONG" if security_ok else "WEAK"

    weights = CONFIG["dimension_weights"]
    scores = {
        "structure": tier_to_score(struct_tier),
        "content_quality": tier_to_score(quality_tier),
        "token_efficiency": tier_to_score(token_tier),
        "security": tier_to_score(security_tier),
    }
    avg_score = weighted_avg(scores, {k: v for k, v in weights.items() if not k.startswith("_")})
    cfg_ov = CONFIG["overall"]

    if not security_ok:
        overall_tier = "WEAK"
    elif avg_score >= cfg_ov["strong_min_avg"]:
        overall_tier = "STRONG"
    elif avg_score >= cfg_ov["moderate_min_avg"]:
        overall_tier = "MODERATE"
    else:
        overall_tier = "WEAK"

    return {
        "name": name,
        "structure": f"{struct_tier} ({struct_pct}%)",
        "content_quality": f"{quality_tier} ({quality_pct}%)",
        "token_efficiency": f"{token_tier} ({token_count} tokens)",
        "security": "PASS" if security_ok else f"FAIL — {', '.join(found_secrets)}",
        "overall": f"{overall_tier} ({avg_to_pct(avg_score)}%)",
        "_struct_tier": struct_tier,
        "_quality_tier": quality_tier,
        "_token_tier": token_tier,
        "_token_count": token_count,
        "_security_ok": security_ok,
        "_secrets": found_secrets,
        "_struct_checks": structure_checks,
        "_quality_checks": quality_checks,
        "_name_len": len(name_text),
        "_desc_len": len(desc_text),
        "_char_count": char_count,
        "_line_count": line_count,
    }

# ── READABLE LABELS ───────────────────────────────────────────────────────────

STRUCTURE_LABELS = {
    "file_is_markdown": "File must be a Markdown (.md) file",
    "filename_kebab_case": "Filename must use lowercase kebab-case convention",
    "yaml_frontmatter_exists": "YAML frontmatter block (---) is missing",
    "required_fields_present": "Required fields 'name' and 'description' must be present",
    "field_length_valid": "Field lengths exceed limits (desc <= 300 chars, name <= 100 chars)",
    "body_size_valid": "File content size is outside the allowed range",
    "has_headings": "Add section headings (## Heading)",
    "under_line_limit": "File exceeds the hard line limit",
    "within_optimal_lines": "File exceeds the optimal line limit — consider trimming",
    "no_absolute_paths": "Remove absolute file paths from content",
    "no_external_urls": "Remove external URLs from content",
}

QUALITY_LABELS = {
    "has_when_to_use": "Add a 'When to Use' section",
    "has_instructions": "Add an instructions or workflow section",
    "has_examples": "Add usage examples",
    "has_multiple_sections": "Add multiple sections using ## headings",
    "no_code_block_leaks": "Remove forbidden code block leaks (e.g. ```python, ```json)",
    "has_structured_tags": "Add structured XML-style tags for better Copilot parsing",
    "no_placeholder_text": "Remove placeholder text such as [TODO] or [INSERT]",
    "has_meaningful_length": "File content is too short — add more detail",
    "section_dominance_met": "Increase structured section coverage (target >= 35% of content)",
    "no_duplicate_phrases": "Remove repeated phrases — content appears redundant",
    "bullets_within_limit": "Shorten bullet points — exceeds recommended word limit",
}

# ── RECOMMENDATIONS ───────────────────────────────────────────────────────────

def recommendations(r: dict) -> list:
    recs = []
    if not r["_security_ok"]:
        recs.append(f"CRITICAL — Remove hardcoded credentials: {', '.join(r['_secrets'])}")
    if r["_struct_tier"] != "STRONG":
        failed = [STRUCTURE_LABELS[k] for k, v in r["_struct_checks"].items() if not v]
        recs.append(f"Structure — {'; '.join(failed)}")
    if r["_quality_tier"] != "STRONG":
        failed = [QUALITY_LABELS[k] for k, v in r["_quality_checks"].items() if not v]
        recs.append(f"Content Quality — {'; '.join(failed)}")
    if r["_token_tier"] != "STRONG":
        limit = CONFIG["token_thresholds"]["strong_max"]
        recs.append(f"Token Efficiency — Reduce file size ({r['_token_count']} tokens; target <= {limit})")
    if not recs:
        recs.append("All checks passed. Ready for adoption.")
    return recs

# ── MARKDOWN REPORT GENERATOR ─────────────────────────────────────────────────

def generate_markdown(results, cfg_s, cfg_tok, dryrun_log):
    lines = []
    collapsible = CONFIG.get("report_format", {}).get("collapsible", False)

    lines.append("# GitHub Copilot Skill Benchmark Report")
    lines.append(f"\n**Skills Evaluated:** {len(results)}\n")
    lines.append("---\n")
    
    # NEW: GitHub CLI output at the very top
    lines.append("## Primary Validation (GitHub CLI)\n")
    lines.append("```text")
    lines.append(dryrun_log)
    lines.append("```\n")
    lines.append("---\n")

    lines.append("## Validation Criteria\n")
    lines.append("| Dimension | Criteria |")
    lines.append("|---|---|")
    lines.append(f"| **Structure** | File format, filename, YAML frontmatter, required fields, desc <= {cfg_s['max_description_chars']} chars, name <= {cfg_s['max_name_chars']} chars, body {cfg_s['min_body_chars']}–{cfg_s['max_body_chars']} chars, headings, lines <= {cfg_s['optimal_line_limit']} optimal / {cfg_s['hard_line_limit']} hard, no absolute paths, no external URLs |")
    lines.append("| **Content Quality** | When-to-use, instructions, examples, multiple sections, no code block leaks, structured tags, no placeholder text, section dominance, no duplicate phrases, bullet word limit |")
    lines.append(f"| **Token Efficiency** | tiktoken cl100k_base — STRONG <= {cfg_tok['strong_max']} tokens, MODERATE <= {cfg_tok['moderate_max']} tokens, WEAK > {cfg_tok['moderate_max']} tokens |")
    lines.append("| **Security** | Hardcoded API keys, tokens, passwords, private keys — PASS / FAIL |")
    lines.append("\n---\n")
    lines.append("## Results\n")
    lines.append("| Skill | Structure | Content Quality | Token Efficiency | Security | Overall |")
    lines.append("|---|---|---|---|---|---|")
    for r in results:
        overall = r["overall"]
        badge = "🟢" if overall.startswith("STRONG") else "🟡" if overall.startswith("MODERATE") else "🔴"
        sec = "PASS" if r["_security_ok"] else "FAIL"
        lines.append(f"| **{r['name']}** | {r['structure']} | {r['content_quality']} | {r['token_efficiency']} | {sec} | {badge} {overall} |")
    lines.append("\n---\n")
    lines.append("## Recommendations\n")
    for r in results:
        overall = r["overall"]
        badge = "🟢" if overall.startswith("STRONG") else "🟡" if overall.startswith("MODERATE") else "🔴"
        if collapsible:
            lines.append("<details>")
            lines.append(f"<summary>{badge} {r['name']} — {overall}</summary>\n")
            for rec in recommendations(r):
                lines.append(f"- {rec}")
            lines.append("\n</details>\n")
        else:
            lines.append(f"### {badge} {r['name']} — {overall}\n")
            for rec in recommendations(r):
                lines.append(f"- {rec}")
            lines.append("")
    lines.append("---\n")
    lines.append("## Conclusion\n")
    strong = [r["name"] for r in results if r["overall"].startswith("STRONG")]
    moderate = [r["name"] for r in results if r["overall"].startswith("MODERATE")]
    weak = [r["name"] for r in results if r["overall"].startswith("WEAK")]
    if strong:
        lines.append(f"**🟢 Ready for Adoption:** {', '.join(strong)}\n")
    if moderate:
        lines.append(f"**🟡 Needs Improvement:** {', '.join(moderate)}\n")
    if weak:
        lines.append(f"**🔴 Not Recommended:** {', '.join(weak)}\n")
    return "\n".join(lines)

# ── REPORT ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark GitHub Copilot skill files.")
    parser.add_argument(
        "skills_root",
        nargs="?",
        default=".github/skills",
        help="Path to folder containing skill subfolders with SKILL.md (default: .github/skills)",
    )
    parser.add_argument(
        "changed_paths",
        nargs="*",
        help="Optional list of changed file paths. When provided, only matching skill folders are evaluated.",
    )
    return parser.parse_args()


def resolve_changed_skill_folders(base: Path, changed_paths: list[str]) -> list[Path]:
    root = Path.cwd().resolve()
    resolved: set[Path] = set()
    skill_path_re = re.compile(r'(?:^|/)\.github/skills/([^/]+)(?:/|$)')

    for raw_path in changed_paths:
        path_text = raw_path.strip()
        if not path_text:
            continue

        normalized = path_text.replace("\\", "/").strip()
        if normalized.startswith("./"):
            normalized = normalized[2:]

        match = skill_path_re.search(normalized)
        if not match:
            continue

        skill_dir = (root / ".github" / "skills" / match.group(1)).resolve()
        if (skill_dir / "SKILL.md").exists() and skill_dir.is_dir():
            try:
                skill_dir.relative_to(base)
            except ValueError:
                continue
            resolved.add(skill_dir)

    return sorted(resolved)


def run():
    args = parse_args()
    base = Path(args.skills_root).resolve()
    if not base.exists() or not base.is_dir():
        print(f"ERROR: Skills root not found or not a directory: {base}")
        sys.exit(1)

    all_folders = sorted([f for f in base.iterdir() if f.is_dir() and (f / "SKILL.md").exists()])
    if not all_folders:
        print(f"ERROR: No skill folders with SKILL.md found under: {base}")
        sys.exit(1)

    if args.changed_paths:
        folders = resolve_changed_skill_folders(base, args.changed_paths)
        if not folders:
            print("No changed/new skill folders with SKILL.md found; skipping skill benchmark.")
            return
    else:
        folders = all_folders

    results = [r for r in (benchmark_skill(f) for f in folders) if r]
    
    # NEW: Run GitHub CLI and capture output
    try:
        cli = subprocess.run(["gh", "skill", "publish", "--dry-run"], cwd=".github", capture_output=True, text=True, check=False)
        dryrun_log = (cli.stdout + "\n" + cli.stderr).strip()
        dryrun_log = dryrun_log.replace("Dry run complete. Use without --dry-run to publish.", "").strip()
        if not dryrun_log:
            dryrun_log = "Dry run executed successfully."
    except Exception as e:
        dryrun_log = f"Failed to execute dry-run: {e}"

    W = 110
    cfg_s = CONFIG["structure"]
    cfg_tok = CONFIG["token_thresholds"]

    print("=" * W)
    print("  GITHUB COPILOT SKILL BENCHMARK REPORT")
    print("=" * W)
    print(f"  Skills Evaluated: {len(results)}\n")

    # NEW: Print CLI Output first
    print("─" * W)
    print("  PRIMARY VALIDATION (GITHUB CLI)")
    print("─" * W)
    for line in dryrun_log.split('\n'):
        if line.strip():
            print(f"  {line}")
    print("")

    criteria = [
        ("Structure",
         f"File format, filename, YAML frontmatter, required fields, "
         f"desc <= {cfg_s['max_description_chars']} chars, name <= {cfg_s['max_name_chars']} chars, "
         f"body {cfg_s['min_body_chars']}–{cfg_s['max_body_chars']} chars, headings, "
         f"lines <= {cfg_s['optimal_line_limit']} optimal / {cfg_s['hard_line_limit']} hard, "
         f"no absolute paths, no external URLs"),
        ("Content Quality",
         "When-to-use, instructions, examples, multiple sections, no code block leaks, "
         "structured tags, no placeholder text, section dominance, no duplicate phrases, bullet word limit"),
        ("Token Efficiency",
         f"tiktoken cl100k_base  |  STRONG <= {cfg_tok['strong_max']}  |  "
         f"MODERATE <= {cfg_tok['moderate_max']}  |  WEAK > {cfg_tok['moderate_max']} tokens"),
        ("Security",
         "Hardcoded API keys, tokens, passwords, private keys — PASS / FAIL"),
    ]

    print("─" * W)
    print("  VALIDATION CRITERIA")
    print("─" * W)
    for dim, desc in criteria:
        print(f"  {dim:<20}  {desc}")

    print("\n" + "─" * W)
    print("  RESULTS")
    print("─" * W)
    c = {"Skill": 30, "Structure": 18, "Quality": 18, "Tokens": 22, "Security": 14, "Overall": 18}
    hdr = (
        f"  {'Skill':<{c['Skill']}} | {'Structure':<{c['Structure']}} | "
        f"{'Content Quality':<{c['Quality']}} | {'Token Efficiency':<{c['Tokens']}} | "
        f"{'Security':<{c['Security']}} | {'Overall':<{c['Overall']}}"
    )
    print(hdr)
    print("  " + "─" * (len(hdr) - 2))
    for r in results:
        print(
            f"  {r['name']:<{c['Skill']}} | {r['structure']:<{c['Structure']}} | "
            f"{r['content_quality']:<{c['Quality']}} | {r['token_efficiency']:<{c['Tokens']}} | "
            f"{r['security']:<{c['Security']}} | {r['overall']:<{c['Overall']}}"
        )

    print("\n" + "─" * W)
    print("  RECOMMENDATIONS")
    print("─" * W)
    for r in results:
        print(f"\n  {r['name']}  →  {r['overall']}")
        for rec in recommendations(r):
            print(f"    • {rec}")

    print("\n" + "─" * W)
    print("  CONCLUSION")
    print("─" * W)
    strong = [r["name"] for r in results if r["overall"].startswith("STRONG")]
    moderate = [r["name"] for r in results if r["overall"].startswith("MODERATE")]
    weak = [r["name"] for r in results if r["overall"].startswith("WEAK")]
    if strong:
        print(f"\n  READY FOR ADOPTION   {', '.join(strong)}")
    if moderate:
        print(f"  NEEDS IMPROVEMENT    {', '.join(moderate)}")
    if weak:
        print(f"  NOT RECOMMENDED      {', '.join(weak)}")
    print("\n" + "=" * W)

    report_path = Path(CONFIG["report"]["report_path"]).resolve()
    report_path.write_text(generate_markdown(results, cfg_s, cfg_tok, dryrun_log), encoding="utf-8")
    dashboard_path = report_path.with_name("skill_benchmark_dashboard.html")
    
    # NEW: Pass dryrun_log to the dashboard
    render_skills_evaluation_dashboard(
        results,
        dashboard_path,
        CONFIG,
        dryrun_log
    )
    print(f"\n  Report saved: {report_path.resolve()}\n")
    print(f"  Dashboard saved: {dashboard_path.resolve()}\n")

if __name__ == "__main__":
    run()
