import os
import sys
import re
import json
import argparse
import tempfile
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

PROMPT_INJECTION_PATTERNS = [
    (r'(?i)\bignore\s+(?:prior|previous|all|above|system)\s+instructions?\b', "Prompt Injection: Ignore Instructions"),
    (r'(?i)\b(?:system\s+override|developer\s+mode|override\s+system)\b', "Prompt Injection: System Override"),
    (r'(?i)\b(?:bypass|disregard|ignore)\s+(?:safety|system|security)?\s*(?:guidelines|rules|constraints|filters)\b', "Prompt Injection: Rule Bypass"),
    (r'(?i)\bforget\s+(?:your\s+)?(?:instructions|rules|constraints)\b', "Prompt Injection: Forget Constraints"),
    (r'(?i)\b(?:you\s+are\s+now\s+a|pretend\s+to\s+be|act\s+as\s+a)\s+(?:developer|admin|administrator|root|jailbreak)\b', "Prompt Injection: Privilege Escalation"),
    (r'(?i)\b(?:dan\s+mode|do\s+anything\s+now|jailbreak)\b', "Prompt Injection: Jailbreak Signature"),
]

def check_shell_security_warning(content: str, fm: dict) -> tuple[bool, list[str]]:
    """
    Validates if allowed-tools contains shell/bash without a security review warning.
    Returns (is_ok, found_issues).
    """
    allowed_tools_val = fm.get("allowed-tools", "")
    if allowed_tools_val is None:
        allowed_tools_val = ""
    
    if not allowed_tools_val:
        match = re.search(r'(?i)allowed-tools\s*:\s*([^\n#]+)', content)
        if match:
            allowed_tools_str = match.group(1)
            lines = content.split('\n')
            start_pos = content.find(match.group(0))
            line_idx = content[:start_pos].count('\n')
            extra_lines = []
            for i in range(line_idx + 1, len(lines)):
                if lines[i].startswith(' ') or lines[i].strip().startswith('-'):
                    extra_lines.append(lines[i].strip())
                else:
                    break
            if extra_lines:
                allowed_tools_str += " " + " ".join(extra_lines)
            allowed_tools_lower = allowed_tools_str.lower()
        else:
            allowed_tools_lower = ""
    else:
        if isinstance(allowed_tools_val, list):
            allowed_tools_lower = " ".join(str(x) for x in allowed_tools_val).lower()
        else:
            allowed_tools_lower = str(allowed_tools_val).lower()

    has_shell = bool(re.search(r'\b(shell|bash|sh|cmd|powershell)\b', allowed_tools_lower))
    
    if has_shell:
        warning_patterns = [
            r'(?i)##?\s*Security\s+(?:Review|Warning)',
            r'(?i)warning:\s*(?:pre-approving\s+)?shell\s+(?:removes\s+confirmation|is\s+sensitive)',
            r'(?i)security\s+review\s+warning',
            r'(?i)approved\s+(?:for\s+shell\s+execution\s+)?after\s+security\s+review',
            r'(?i)<!--\s*security\s+review\s+warning\s*-->'
        ]
        has_warning = any(re.search(pat, content) for pat in warning_patterns)
        if not has_warning:
            return False, ["Shell Tool Without Security Warning"]
            
    return True, []

def check_security(content: str, fm: dict = None) -> tuple[bool, list[str]]:
    found_issues = [label for pattern, label in SECURITY_PATTERNS if re.search(pattern, content)]
    
    if fm is None:
        _, fm = parse_frontmatter(content)
        
    shell_ok, shell_issues = check_shell_security_warning(content, fm)
    if not shell_ok:
        found_issues.extend(shell_issues)
        
    for pattern, label in PROMPT_INJECTION_PATTERNS:
        if re.search(pattern, content):
            found_issues.append(label)
            
    return len(found_issues) == 0, found_issues

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
        elif current_key and (line.startswith(' ') or line.strip().startswith('-')):
            val = line.strip()
            if val.startswith('-'):
                val = val[1:].strip()
            current_value.append(val)
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

def to_kebab_case(s: str) -> str:
    s = s.strip()
    s = re.sub(r'[^a-zA-Z0-9]+', '-', s)
    s = re.sub(r'(?<=[a-z0-9])([A-Z])', r'-\1', s)
    return s.lower().strip('-')

def run_structure_checks(skill_file, name, content, has_frontmatter,
                         has_name, has_desc, desc_text, name_text, char_count):
    cfg_s = CONFIG["structure"]
    lines = content.splitlines()
    
    max_desc = cfg_s.get("max_description_chars", 1024)
    max_name = cfg_s.get("max_name_chars", 64)
    
    match_fm = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    body_char_count = len(content[match_fm.end():]) if match_fm else len(content)
    
    # Markdown links verification
    links = re.findall(r'\[.*?\]\(([^)]+)\)', content)
    
    # Check for external URLs
    has_raw_external_url = bool(re.search(r'\bhttps?(?::|//)', content, re.IGNORECASE))
    has_parsed_external_link = False
    for p in links:
        match_scheme = re.match(r'^([a-zA-Z][a-zA-Z0-9.+-]*):', p)
        if match_scheme:
            scheme = match_scheme.group(1)
            if len(scheme) != 1:
                has_parsed_external_link = True
                break
                
    no_external_urls_val = not (has_raw_external_url or has_parsed_external_link)

    results = {
        "file_is_markdown": skill_file.suffix == ".md",
        "filename_kebab_case": bool(re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name)),
        "yaml_frontmatter_exists": has_frontmatter,
        "required_fields_present": has_name and has_desc,
        "field_length_valid": (
            0 < len(desc_text) <= max_desc and
            0 < len(name_text) <= max_name
        ),
        "body_size_valid": cfg_s["min_body_chars"] <= body_char_count <= cfg_s["max_body_chars"],
        "has_headings": bool(re.search(r'^#{1,3} .+', content, re.MULTILINE)),
        "under_line_limit": len(lines) <= cfg_s["hard_line_limit"],
        "within_optimal_lines": len(lines) <= cfg_s["optimal_line_limit"],
        "no_absolute_paths": not bool(re.search(r'\b[A-Za-z]:[/\\]|/(?:bin|usr|etc|var|opt|lib|tmp|home|root)\b', content, re.IGNORECASE)),
        "no_external_urls": no_external_urls_val,
    }
    
    # New structural checks
    results["name_no_xml_tags"] = not bool(re.search(r'<[^>]+>', name_text))
    
    reserved_words = cfg_s.get("reserved_words", ["anthropic", "claude"])
    results["name_no_reserved_words"] = not any(w in name_text.lower() for w in reserved_words)
    
    results["directory_matches_skill_name"] = to_kebab_case(name_text) == to_kebab_case(skill_file.parent.name)
    
    local_links = []
    for p in links:
        p_lower = p.lower()
        if p_lower.startswith('#'):
            continue
        match_scheme = re.match(r'^([a-zA-Z][a-zA-Z0-9.+-]*):', p_lower)
        if match_scheme:
            scheme = match_scheme.group(1)
            if len(scheme) != 1:
                # Treat as external link, skip local link validation
                continue
        local_links.append(p)
        
    allowed_res = set(cfg_s.get("allowed_resource_extensions", [".md", ".json", ".yaml", ".yml", ".csv", ".xml", ".txt"]))
    allowed_scr = set(cfg_s.get("allowed_script_extensions", [".py", ".js", ".sh", ".ps1"]))
    script_suffixes = {'.py', '.js', '.sh', '.ps1', '.bat', '.cmd', '.rb', '.pl'}
    
    valid_res_ext = True
    valid_scr_ext = True
    
    for link in local_links:
        link_stripped = link.strip()
        if not link_stripped:
            continue
        path_part = link_stripped.split()[0].strip('"' + "'")
        clean_path = path_part.split('?')[0].split('#')[0].strip()
        
        # Normalize ./ and .\ paths
        if clean_path.startswith('./') or clean_path.startswith('.\\'):
            clean_path = clean_path[2:]
            
        is_relative = not (clean_path.startswith('/') or clean_path.startswith('\\') or re.match(r'^[A-Za-z]:', clean_path) or '..' in clean_path)
        depth_ok = (clean_path.count('/') + clean_path.count('\\')) <= 1
        suffix = Path(clean_path).suffix.lower()
        
        if suffix:
            if suffix in script_suffixes or suffix in allowed_scr:
                if not (is_relative and depth_ok and suffix in allowed_scr):
                    valid_scr_ext = False
            else:
                if not (is_relative and depth_ok and suffix in allowed_res):
                    valid_res_ext = False
        else:
            if not (is_relative and depth_ok):
                valid_res_ext = False
                
    results["valid_resource_file_extensions"] = valid_res_ext
    results["valid_script_file_extensions"] = valid_scr_ext
    
    return results

# ── CONTENT QUALITY CHECKS ────────────────────────────────────────────────────
# Validates when-to-use, instructions, examples, sections, tags,
# code block leaks, placeholder text, meaningful length,
# section dominance, duplicate phrases, and bullet length.

def run_quality_checks(content, char_count, line_count=0, folder_path=None):
    cfg_cq = CONFIG["content_quality"]
    forbidden_blocks = ["```python", "```json", "```yaml", "```javascript", "```bash"]

    section_matches = re.findall(r'(?:^|\n)## .{1,80}\n(.*?)(?=\n## |\Z)', content, re.DOTALL)
    section_content = " ".join(section_matches)
    section_ratio = len(section_content) / char_count if char_count > 0 else 0

    words = content.lower().split()
    phrase_len = cfg_cq["duplicate_phrase_words"]
    min_repeats = cfg_cq["duplicate_phrase_min"]
    phrases = [" ".join(words[i:i+phrase_len]) for i in range(len(words) - phrase_len + 1)]
    phrase_counts = {}
    for p in phrases:
        phrase_counts[p] = phrase_counts.get(p, 0) + 1
    has_duplicates = any(v >= min_repeats for v in phrase_counts.values())

    bullets = re.findall(r'^\s*[-*]\s+(.+)', content, re.MULTILINE)
    bullets_ok = all(len(b.split()) <= cfg_cq["bullet_word_limit"] for b in bullets) if bullets else True

    min_meaningful_len = cfg_cq.get("min_meaningful_length", 200)

    results = {
        "has_when_to_use": bool(re.search(r'##?\s*(when to use|trigger|use case)', content, re.IGNORECASE)),
        "has_instructions": bool(re.search(r'##?\s*(instruction|workflow|step|how to|usage)', content, re.IGNORECASE)),
        "has_examples": bool(re.search(r'##?\s*(example|sample)', content, re.IGNORECASE)),
        "has_multiple_sections": content.count('## ') >= 2,
        "no_code_block_leaks": not any(b in content for b in forbidden_blocks),
        "has_structured_tags": bool(re.search(r'<[a-zA-Z][^>]{0,50}>', content)),
        "no_placeholder_text": not bool(re.search(r'\[TODO\]|\[PLACEHOLDER\]|\[INSERT\]', content, re.IGNORECASE)),
        "has_meaningful_length": char_count > min_meaningful_len,
        "section_dominance_met": section_ratio >= cfg_cq["section_dominance_pct"],
        "no_duplicate_phrases": not has_duplicates,
        "bullets_within_limit": bullets_ok,
    }

    # Description quality checks (CQ-12, CQ-13, CQ-14)
    has_fm, fm = parse_frontmatter(content)
    desc_text = fm.get("description", "") if has_fm else ""
    
    action_pattern = r'\b(allow|enable|provide|perform|run|evaluate|check|scan|generate|create|update|manage|automate|help|process|analyze)\w*\b'
    trigger_pattern = r'\b(when|trigger|use\s+case|scenario|use\s+this|whenever|useful\s+for|if\s+you|applicable)\b'
    results["desc_what_and_when"] = bool(re.search(action_pattern, desc_text, re.IGNORECASE)) and bool(re.search(trigger_pattern, desc_text, re.IGNORECASE))
    
    neg_pattern = r'\b(not|avoid|do not|don\'t|except|unless|instead|when not)\b'
    results["desc_negative_cases"] = bool(re.search(neg_pattern, desc_text, re.IGNORECASE))
    
    generic_pattern = r'^(helps\s+with|processes|manages|handles|deals\s+with)\s+\w+$'
    is_not_generic = not bool(re.search(generic_pattern, desc_text.strip(), re.IGNORECASE))
    results["desc_not_vague"] = len(desc_text) >= cfg_cq.get("min_description_chars", 30) and is_not_generic
    
    # Instructions step directives check (CQ-15)
    inst_match = re.search(r'^(##?\s*(?:instructions?|workflows?|steps?|how\s+to|usage).*?)(?=\n##? |\Z)', content, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    instructions_block = inst_match.group(1) if inst_match else ""
    steps = []
    if instructions_block:
        for line in instructions_block.splitlines():
            m = re.match(r'^\s*(?:[-*+]|\d+\.)\s+(.+)', line)
            if m:
                steps.append(m.group(1).strip())
                
    if steps:
        verbs = cfg_cq.get("imperative_verbs", ["run", "execute", "use", "create", "verify", "update", "write", "add", "remove", "delete", "check", "validate", "deploy", "build", "test", "ensure", "always", "never", "do", "configure", "setup", "analyze", "review", "generate", "format", "implement", "integrate", "install", "track", "document", "audit", "commit", "push", "pull", "merge", "fix", "refactor", "inspect", "clean", "compile"])
        verbs_set = {v.lower() for v in verbs}
        
        imperative_count = 0
        for s in steps:
            s_clean = s.lstrip('*_`').strip()
            parts = s_clean.split()
            if not parts:
                continue
            first_word = parts[0]
            strip_chars = '*_`!"#$%&\'()*+,-./:;<=>?@[\\]^{|}~'
            cleaned_word = first_word.strip(strip_chars).lower()
            if cleaned_word in verbs_set:
                imperative_count += 1
                
        pct_imperative = (imperative_count / len(steps)) * 100
        min_imp_pct = cfg_cq.get("min_imperative_pct", 0.70)
        target_pct = min_imp_pct * 100 if min_imp_pct <= 1.0 else min_imp_pct
        results["instructions_use_directives"] = pct_imperative >= target_pct
    else:
        results["instructions_use_directives"] = False
        
    # Gotchas section (CQ-16)
    gotchas_pats = cfg_cq.get("gotchas_keywords", ["gotcha", "edge case", "limitation", "pitfall", "known issue", "constraint"])
    gotchas_esc = '|'.join(re.escape(k) for k in gotchas_pats)
    results["has_gotchas_section"] = bool(re.search(r'^##?\s*(?:' + gotchas_esc + r')s?\b', content, re.IGNORECASE | re.MULTILINE))
    
    # Output templates (CQ-17)
    output_pats = cfg_cq.get("output_template_keywords", ["output template", "template", "response format", "output format", "format template"])
    output_esc = '|'.join(re.escape(k) for k in output_pats)
    has_output_heading = bool(re.search(r'^##?\s*(?:' + output_esc + r')\b', content, re.IGNORECASE | re.MULTILINE))
    has_xml_template = bool(re.search(r'<template>.*?</template>', content, re.IGNORECASE | re.DOTALL))
    results["has_output_templates"] = has_output_heading or has_xml_template
    
    # Validation loops (CQ-18)
    val_loop_pats = cfg_cq.get("validation_loop_keywords", ["verify that", "check if", "repeat until", "if not, correct", "validation loop", "retry", "run tests to verify", "ensure the output"])
    val_loop_esc = '|'.join(re.escape(k) for k in val_loop_pats)
    results["has_validation_loops"] = bool(re.search(r'\b(?:' + val_loop_esc + r')\b', content, re.IGNORECASE))
    
    # Local references extraction
    links = re.findall(r'\[.*?\]\(([^)]+)\)', content)
    local_links = []
    for p in links:
        p_lower = p.lower()
        if p_lower.startswith('#'):
            continue
        match_scheme = re.match(r'^([a-zA-Z][a-zA-Z0-9.+-]*):', p_lower)
        if match_scheme:
            scheme = match_scheme.group(1)
            if len(scheme) != 1:
                continue
        local_links.append(p)
        
    # Progressive disclosure (CQ-19)
    has_file_references = len(local_links) > 0
    prog_limit = cfg_cq.get("progressive_disclosure_line_limit", 300)
    if line_count > prog_limit:
        results["progressive_disclosure"] = has_file_references
    else:
        results["progressive_disclosure"] = True
        
    # Table of Contents check for referenced markdown files (CQ-20)
    toc_ok = True
    if folder_path:
        toc_limit = cfg_cq.get("reference_file_toc_line_limit", 100)
        for link in local_links:
            link_stripped = link.strip()
            if not link_stripped:
                continue
            path_part = link_stripped.split()[0].strip('"' + "'")
            clean_path = path_part.split('?')[0].split('#')[0].strip()
            if clean_path.startswith('./') or clean_path.startswith('.\\'):
                clean_path = clean_path[2:]
            if not clean_path.lower().endswith('.md'):
                continue
            ref_path = (folder_path / clean_path).resolve()
            if ref_path.exists() and ref_path.is_file():
                try:
                    ref_content = ref_path.read_text(encoding="utf-8-sig")
                    ref_lines = len(ref_content.splitlines())
                    if ref_lines > toc_limit:
                        has_toc_heading = bool(re.search(r'^##?\s*(?:table\s+of\s+contents|toc)', ref_content, re.IGNORECASE | re.MULTILINE))
                        has_internal_links = bool(re.search(r'\[.*?\]\(#[a-zA-Z0-9\-_]+\)', ref_content))
                        if not (has_toc_heading or has_internal_links):
                            toc_ok = False
                            break
                except Exception:
                    pass
    results["toc_for_long_references"] = toc_ok
    
    return results

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
        content = skill_file.read_text(encoding="utf-8-sig")
    except Exception as e:
        error_msg = str(e)
        return {
            "name": folder_path.name,
            "structure": "WEAK (0.0%)",
            "content_quality": "WEAK (0.0%)",
            "token_efficiency": "WEAK (0 tokens)",
            "security": "FAIL",
            "overall": "WEAK (0.0%)",
            "_struct_tier": "WEAK",
            "_quality_tier": "WEAK",
            "_token_tier": "WEAK",
            "_token_count": 0,
            "_security_ok": False,
            "_secrets": [],
            "_struct_checks": {k: False for k in STRUCTURE_LABELS.keys()},
            "_quality_checks": {k: False for k in QUALITY_LABELS.keys()},
            "_name_len": 0,
            "_desc_len": 0,
            "_char_count": 0,
            "_line_count": 0,
            "error": error_msg,
        }

    name = folder_path.name
    char_count = len(content)
    line_count = len(content.splitlines())
    cfg_cq = CONFIG["content_quality"]
    cfg_struct = CONFIG["structure"]

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
    struct_tier = pct_to_tier(struct_pct, cfg_struct.get("good_min_pct", 85), cfg_struct.get("average_min_pct", 50))

    quality_checks = run_quality_checks(content, char_count, line_count=line_count, folder_path=folder_path)
    quality_pct = round(sum(quality_checks.values()) / len(quality_checks) * 100, 1)
    quality_tier = pct_to_tier(quality_pct, cfg_cq["good_min_pct"], cfg_cq["average_min_pct"])

    token_tier, token_count = run_token_check(content)

    security_ok, found_secrets = check_security(content, fm)
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
    "file_is_markdown": "Skill file must be Markdown (.md) format",
    "filename_kebab_case": "Folder name must use lowercase-kebab-case (e.g., my-skill-name)",
    "yaml_frontmatter_exists": "File must start with a YAML metadata block (--- ... ---)",
    "required_fields_present": "'name' and 'description' fields required in YAML frontmatter",
    "field_length_valid": "name <=64 chars, description <=1024 chars",
    "body_size_valid": "Body content must be between 30 and 15,000 characters",
    "has_headings": "Organize content using section headings (## Instructions)",
    "under_line_limit": "File exceeds 500-line hard limit",
    "within_optimal_lines": "File exceeds 200-line optimal limit",
    "no_absolute_paths": "Use relative paths only, no C:\\ or /usr/ paths",
    "no_external_urls": "Remove external web links (http/https URLs)",
    "name_no_xml_tags": "Skill name must not contain HTML/XML tags",
    "name_no_reserved_words": "Skill name must not use platform-reserved terms",
    "directory_matches_skill_name": "Folder name must match the 'name' field in YAML",
    "valid_resource_file_extensions": "Referenced files must use approved formats (.md, .json, .yaml)",
    "valid_script_file_extensions": "Referenced scripts must use approved formats (.py, .js, .sh)",
}

QUALITY_LABELS = {
    "has_when_to_use": "Include a 'when to use' section with trigger scenarios",
    "has_instructions": "Include an instructions section with step-by-step workflow",
    "has_examples": "Include an examples section with usage samples",
    "has_multiple_sections": "Organize content into at least 2 sections with ## headings",
    "no_code_block_leaks": "Remove raw code blocks (```python, ```json)",
    "has_structured_tags": "Use XML-style tags (<context>, <rules>) for AI parsing",
    "no_placeholder_text": "Remove placeholder markers like [TODO] or [INSERT]",
    "has_meaningful_length": "Content too short, expand with details (min 200 chars)",
    "section_dominance_met": "At least 35% of content should be inside organized sections",
    "no_duplicate_phrases": "Remove repeated phrases, each sentence should add unique value",
    "bullets_within_limit": "Keep bullet points concise, max 125 words per bullet",
    "desc_what_and_when": "Description must explain WHAT the skill does AND WHEN to use it",
    "desc_negative_cases": "Description should specify WHEN NOT to use this skill",
    "desc_not_vague": "Description must be specific, not generic like 'helps with tasks'",
    "instructions_use_directives": "Instructions should use directive verbs (direct action commands like Run, Create, Verify)",
    "has_gotchas_section": "Include a gotchas section (documents known pitfalls and edge cases)",
    "has_output_templates": "Define output templates (expected response format)",
    "has_validation_loops": "Include verification steps (self-check loops to confirm correctness)",
    "progressive_disclosure": "Skills over 300 lines should split details into reference files",
    "toc_for_long_references": "Referenced .md files over 100 lines must include a table of contents",
}

# ── RECOMMENDATIONS ───────────────────────────────────────────────────────────

def recommendations(r: dict) -> list:
    recs = []
    if not r["_security_ok"]:
        recs.append(f"CRITICAL — Security issues found: {', '.join(r['_secrets'])}")
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

def generate_markdown(results, cfg_s, cfg_tok):
    lines = []
    collapsible = CONFIG.get("report_format", {}).get("collapsible", False)

    lines.append("# GitHub Copilot Skill Benchmark Report")
    lines.append(f"\n**Skills Evaluated:** {len(results)}\n")
    lines.append("---\n")
    lines.append("## Validation Criteria\n")
    lines.append("| Dimension | Criteria |")
    lines.append("|---|---|")
    lines.append(f"| **Structure** | File format, filename, YAML frontmatter, required fields, desc <= {cfg_s['max_description_chars']} chars, name <= {cfg_s['max_name_chars']} chars, body {cfg_s['min_body_chars']}–{cfg_s['max_body_chars']} chars, headings, lines <= {cfg_s['optimal_line_limit']} optimal / {cfg_s['hard_line_limit']} hard, no absolute paths, no external URLs |")
    lines.append("| **Content Quality** | When-to-use, instructions, examples, multiple sections, no code block leaks, structured tags, no placeholder text, section dominance, no duplicate phrases, bullet word limit, description completeness, negative cases, imperative directives, gotchas/edge cases, output templates, validation loops, progressive disclosure, TOC for reference files |")
    lines.append(f"| **Token Efficiency** | tiktoken cl100k_base — STRONG <= {cfg_tok['strong_max']} tokens, MODERATE <= {cfg_tok['moderate_max']} tokens, WEAK > {cfg_tok['moderate_max']} tokens |")
    lines.append("| **Security** | Hardcoded API keys/tokens, shell tool security warnings, prompt injection patterns — PASS / FAIL |")
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

        skill_dir = (base / match.group(1)).resolve()
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
    W = 110
    cfg_s = CONFIG["structure"]
    cfg_tok = CONFIG["token_thresholds"]

    print("=" * W)
    print("  GITHUB COPILOT SKILL BENCHMARK REPORT")
    print("=" * W)
    print(f"  Skills Evaluated: {len(results)}\n")

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
    report_path.write_text(generate_markdown(results, cfg_s, cfg_tok), encoding="utf-8")
    dashboard_path = report_path.with_name("skill_benchmark_dashboard.html")
    render_skills_evaluation_dashboard(
        results,
        dashboard_path,
        CONFIG,
    )
    print(f"\n  Report saved: {report_path.resolve()}\n")
    print(f"  Dashboard saved: {dashboard_path.resolve()}\n")

if __name__ == "__main__":
    run()
