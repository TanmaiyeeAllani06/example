import html
import re
from pathlib import Path


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


# ── MAIN RENDER FUNCTION ──────────────────────────────────────────────────────

def render_skills_evaluation_dashboard(
    results: list[dict],
    output_path,
    config: dict | None = None,
    dryrun_log: str = "",  
) -> None:
    """Render an interactive HTML dashboard from skill benchmark results."""
    output_path = Path(output_path)
    config = config or {}

    strong   = [r for r in results if r["overall"].startswith("STRONG")]
    moderate = [r for r in results if r["overall"].startswith("MODERATE")]
    weak     = [r for r in results if r["overall"].startswith("WEAK")]
    sec_fail = [r for r in results if not r.get("_security_ok", True)]

    total          = len(results)
    avg_overall    = round(sum(_extract_pct(r["overall"]) for r in results) / total, 1) if total else 0.0
    strong_pct     = round(len(strong)   / total * 100, 1) if total else 0.0
    moderate_pct   = round(len(moderate) / total * 100, 1) if total else 0.0
    weak_pct       = round(len(weak)     / total * 100, 1) if total else 0.0
    sec_pass_pct   = round((total - len(sec_fail)) / total * 100, 1) if total else 0.0

    rows        = []
    issue_cards = []

    for idx, result in enumerate(sorted(results, key=lambda r: _extract_pct(r["overall"]), reverse=True)):
        name        = html.escape(result["name"])
        struct_pct  = _extract_pct(result["structure"])
        quality_pct = _extract_pct(result["content_quality"])
        token_pct   = _token_visual_score(result)
        sec_ok      = result.get("_security_ok", True)
        sec_pct     = 100 if sec_ok else 0
        sec_label   = "PASS" if sec_ok else "FAIL"

        rows.append(f"""
        <tr>
          <td class="skill-name">{name}</td>
          <td><span class="pill {_tier_class(result['overall'])}">{html.escape(result['overall'])}</span></td>
          <td>{_dimension_cell(struct_pct,  result['structure'])}</td>
          <td>{_dimension_cell(quality_pct, result['content_quality'])}</td>
          <td>{_dimension_cell(token_pct,   result['token_efficiency'])}</td>
          <td>{_dimension_cell(sec_pct,     sec_label)}</td>
        </tr>""")

        grouped = _group_recommendations(result, config)
        if grouped:
            issue_cards.append(_issue_card(result, grouped, idx))

    if not issue_cards:
        issue_cards.append("""
        <article class="issue-card">
          <div class="issue-head">
            <strong>All skills</strong>
            <span class="pill strong">READY</span>
          </div>
          <div class="issue-section">
            <div class="issue-category">Status</div>
            <div class="issue-items"><span>No benchmark issues found</span></div>
          </div>
        </article>""")

        dryrun_html = ""
    if dryrun_log:
        dryrun_html = f"""
        <section class="panel">
          <div class="panel-head"><h2>CLI Validation (gh skill publish --dry-run)</h2></div>
          <div style="background: #111827; color: #e2e8f0; padding: 16px; border-radius: 8px; overflow-x: auto; font-family: Consolas, monospace; font-size: 13px; line-height: 1.4;">
            <pre style="margin: 0;">{html.escape(dryrun_log.strip())}</pre>
          </div>
        </section>
        """

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GitHub Copilot Skill Benchmark Dashboard</title>
<style>
  :root {{
    --page: #edf3f8;
    --card: #ffffff;
    --ink: #111827;
    --muted: #52657d;
    --line: #cdd9e6;
    --blue: #2f76b7;
    --blue-soft: #d9eafb;
    --green: #20784a;
    --green-soft: #d8f1df;
    --amber: #d99a22;
    --amber-soft: #ffe6aa;
    --red: #c84a40;
    --red-soft: #ffd9d5;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--page);
    color: var(--ink);
    font-family: "Segoe UI", Aptos, Arial, sans-serif;
    font-size: 14px;
    line-height: 1.5;
  }}
  main {{
    width: calc(100% - 36px);
    margin: 18px auto 40px;
    display: flex;
    flex-direction: column;
    gap: 14px;
  }}
  header, .panel, .summary-strip, .issue-card {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: 0 4px 16px rgba(16, 24, 40, 0.07);
  }}
  header {{
    padding: 22px 26px;
  }}
  h1 {{
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.3px;
  }}
  .subtitle {{
    color: var(--muted);
    font-size: 14px;
    margin-top: 6px;
  }}
  .summary-strip {{
    padding: 14px;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 10px;
  }}
  .rail-metric {{
    display: grid;
    grid-template-columns: 82px 1fr;
    gap: 12px;
    align-items: center;
    padding: 12px;
    border: 1px solid #e3eaf2;
    border-radius: 8px;
    background: #fbfdff;
  }}
  .ring {{
    width: 78px; height: 78px;
    display: grid; place-items: center;
    border-radius: 50%;
    background: conic-gradient(var(--color) calc(var(--value) * 1%), #e5edf5 0);
    position: relative;
  }}
  .ring::after {{
    content: "";
    position: absolute;
    inset: 11px;
    background: #fff;
    border-radius: 50%;
  }}
  .ring span {{
    position: relative;
    z-index: 1;
    font-size: 14px;
    font-weight: 800;
  }}
  .rail-metric strong {{
    display: block;
    font-size: 13px;
    font-weight: 700;
  }}
  .rail-metric small {{
    display: block;
    margin-top: 2px;
    color: var(--muted);
    font-size: 11px;
  }}
  .panel {{
    padding: 20px 22px;
  }}
  .panel-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 14px;
  }}
  h2 {{
    font-size: 20px;
    font-weight: 700;
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    color: var(--muted);
    font-size: 12px;
  }}
  .dot {{
    display: inline-block;
    width: 9px; height: 9px;
    border-radius: 50%;
    margin-right: 4px;
  }}
  .stacked {{
    display: flex;
    height: 20px;
    overflow: hidden;
    border-radius: 999px;
    background: #e5edf5;
  }}
  .seg-strong   {{ width: {strong_pct}%;   background: var(--green); }}
  .seg-moderate {{ width: {moderate_pct}%; background: var(--amber); }}
  .seg-weak     {{ width: {weak_pct}%;     background: var(--red); }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  col.c-skill   {{ width: 22%; }}
  col.c-overall {{ width: 14%; }}
  col.c-metric  {{ width: 16%; }}
  th, td {{
    padding: 12px 10px;
    border-bottom: 1px solid #e3eaf2;
    text-align: left;
    vertical-align: middle;
  }}
  th {{
    color: var(--muted);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}
  .skill-name {{ font-weight: 700; overflow-wrap: anywhere; }}
  .pill {{
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 800;
    white-space: nowrap;
  }}
  .strong  {{ background: var(--green-soft);  color: var(--green); }}
  .moderate{{ background: var(--amber-soft);  color: #8c5f00; }}
  .weak    {{ background: var(--red-soft);    color: #9c342b; }}
  .dimension-cell {{ display: grid; gap: 5px; }}
  .mini-bar {{
    width: 100%; height: 10px;
    background: #e5edf5;
    border-radius: 999px;
    overflow: hidden;
  }}
  .mini-bar span {{
    display: block; height: 100%;
    background: var(--blue);
  }}
  .dimension-cell > .dim-label {{
    color: #364a63;
    font-size: 12px;
    line-height: 1.35;
  }}
  .issue-list {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 14px;
  }}
  .issue-card {{ padding: 16px; }}
  .issue-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }}
  .issue-head strong {{
    font-size: 14px;
    font-weight: 700;
    overflow-wrap: anywhere;
  }}
  .issue-section {{
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 8px;
    padding: 10px 0;
    border-top: 1px solid #e8eef5;
  }}
  .issue-category {{
    color: var(--blue);
    font-size: 11px;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding-top: 2px;
  }}
  .issue-items {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: flex-start;
  }}
  .issue-items span.tag {{
    padding: 5px 8px;
    border-radius: 6px;
    background: var(--blue-soft);
    color: #244763;
    font-size: 11px;
    font-weight: 700;
  }}
  .extra-wrap {{
    display: contents;
  }}
  .extra-wrap.collapsed {{
    display: none;
  }}
  .expand-btn {{
    padding: 5px 10px;
    border-radius: 6px;
    background: var(--blue);
    color: #fff;
    font-size: 11px;
    font-weight: 800;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
    border: none;
    outline: none;
    font-family: inherit;
  }}
  .expand-btn:hover {{ background: #1d5f9c; }}
  @media (max-width: 1180px) {{
    .summary-strip {{ grid-template-columns: repeat(2, 1fr); }}
    .issue-list    {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (max-width: 760px) {{
    main {{ width: calc(100% - 20px); }}
    h1   {{ font-size: 22px; }}
    .summary-strip, .issue-list {{ grid-template-columns: 1fr; }}
    .issue-section {{ grid-template-columns: 1fr; gap: 4px; }}
    table {{ display: block; overflow-x: auto; min-width: 900px; }}
  }}
</style>
</head>
<body>
<main>
  <header>
    <h1>GitHub Copilot Skill Benchmark Dashboard</h1>
    <p class="subtitle">Structure &middot; Content Quality &middot; Token Efficiency &middot; Security &middot; Overall readiness</p>
  </header>

  <section class="summary-strip">
    {_ring("Avg overall",    avg_overall,  f"{total} skills evaluated",      "var(--blue)")}
    {_ring("Strong",         strong_pct,   f"{len(strong)} skills",          "var(--green)")}
    {_ring("Moderate",       moderate_pct, f"{len(moderate)} skills",        "var(--amber)")}
    {_ring("Weak",           weak_pct,     f"{len(weak)} skills",            "var(--red)")}
    {_ring("Security pass",  sec_pass_pct, f"{len(sec_fail)} failure(s)",    "var(--green)")}
  </section>

  <section class="panel">
    <div class="panel-head">
      <h2>Readiness Split</h2>
      <div class="legend">
        <span><i class="dot" style="background:var(--green)"></i>Strong {len(strong)}</span>
        <span><i class="dot" style="background:var(--amber)"></i>Moderate {len(moderate)}</span>
        <span><i class="dot" style="background:var(--red)"></i>Weak {len(weak)}</span>
      </div>
    </div>
    <div class="stacked">
      <span class="seg-strong"></span>
      <span class="seg-moderate"></span>
      <span class="seg-weak"></span>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head"><h2>Benchmark Matrix</h2></div>
    <table>
      <colgroup>
        <col class="c-skill"><col class="c-overall">
        <col class="c-metric"><col class="c-metric">
        <col class="c-metric"><col class="c-metric">
      </colgroup>
      <thead>
        <tr>
          <th>Skill</th><th>Overall</th>
          <th>Structure</th><th>Content Quality</th>
          <th>Token Efficiency</th><th>Security</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>

  <section class="panel">
    <div class="panel-head"><h2>Improvement Focus</h2></div>
    <div class="issue-list">{''.join(issue_cards)}</div>
  </section>
  {dryrun_html}

</main>

<script>
function toggleExpand(btn) {{
  var wrap = btn.previousElementSibling;
  var collapsed = wrap.classList.toggle("collapsed");
  var count = btn.dataset.count;
  btn.textContent = collapsed ? ("+" + count + " more") : "show less";
}}
</script>
</body>
</html>"""

    output_path.write_text(html_doc, encoding="utf-8")


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _extract_pct(label: str) -> float:
    m = re.search(r"\(([\d.]+)%\)", label)
    return float(m.group(1)) if m else 0.0


def _tier_class(label: str) -> str:
    if label.startswith("STRONG") or label == "PASS":
        return "strong"
    if label.startswith("MODERATE"):
        return "moderate"
    return "weak"


def _bar_width(value: float) -> float:
    return max(0.0, min(100.0, value))


def _token_visual_score(result: dict) -> int:
    tier = result.get("_token_tier", "WEAK")
    return 100 if tier == "STRONG" else 65 if tier == "MODERATE" else 30


def _dimension_cell(score: float, label: str) -> str:
    return (
        f'<div class="dimension-cell">'
        f'<div class="mini-bar"><span style="width:{_bar_width(score):.1f}%"></span></div>'
        f'<span class="dim-label">{html.escape(label)}</span>'
        f'</div>'
    )


def _ring(label: str, value: float, note: str, color: str) -> str:
    return (
        f'<div class="rail-metric">'
        f'<div class="ring" style="--value:{_bar_width(value):.1f}; --color:{color};">'
        f'<span>{value:.1f}%</span></div>'
        f'<div><strong>{html.escape(label)}</strong>'
        f'<small>{html.escape(note)}</small></div>'
        f'</div>'
    )


def _issue_card(result: dict, grouped: list[tuple[str, list[str]]], card_idx: int) -> str:
    """
    Build an issue card. Each category shows the first VISIBLE_LIMIT items,
    then a clickable button to expand/collapse the rest.
    """
    VISIBLE_LIMIT = 4
    sections = []

    for cat_idx, (category, parts) in enumerate(grouped):
        visible = parts[:VISIBLE_LIMIT]
        hidden  = parts[VISIBLE_LIMIT:]

        visible_html = "".join(
            f'<span class="tag">{html.escape(p)}</span>' for p in visible
        )

        extra_html = ""
        btn_html   = ""
        if hidden:
            uid = f"ex_{card_idx}_{cat_idx}"
            extra_html = (
                f'<span class="extra-wrap collapsed" id="{uid}">'
                + "".join(f'<span class="tag">{html.escape(p)}</span>' for p in hidden)
                + '</span>'
            )
            btn_html = (
                f'<button class="expand-btn" '
                f'data-count="{len(hidden)}" '
                f'onclick="toggleExpand(this)">+{len(hidden)} more</button>'
            )

        sections.append(
            f'<div class="issue-section">'
            f'<div class="issue-category">{html.escape(category)}</div>'
            f'<div class="issue-items">'
            f'{visible_html}{extra_html}{btn_html}'
            f'</div></div>'
        )

    return (
        f'<article class="issue-card">'
        f'<div class="issue-head">'
        f'<strong>{html.escape(result["name"])}</strong>'
        f'<span class="pill {_tier_class(result["overall"])}">{html.escape(result["overall"])}</span>'
        f'</div>'
        + "".join(sections)
        + '</article>'
    )


def _group_recommendations(result: dict, config: dict) -> list[tuple[str, list[str]]]:
    grouped = []

    if not result.get("_security_ok", True):
        secrets = result.get("_secrets", [])
        grouped.append(("Security", [f"Remove hardcoded credentials: {', '.join(secrets)}"]))

    struct_issues = _structure_issues(result, config)
    if struct_issues:
        grouped.append(("Structure", struct_issues))

    quality_issues = _quality_issues(result)
    if quality_issues:
        grouped.append(("Content Quality", quality_issues))

    if result.get("_token_tier") != "STRONG":
        cfg_tok = config.get("token_thresholds", {})
        limit = cfg_tok.get("strong_max", "configured")
        count = result.get("_token_count", 0)
        grouped.append(("Token Efficiency", [f"{count}/{limit} tokens (STRONG threshold)"]))

    return [(cat, items) for cat, items in grouped if items]


def _structure_issues(result: dict, config: dict) -> list[str]:
    cfg = config.get("structure", {})
    checks = result.get("_struct_checks", {})
    issues = []

    for key, passed in checks.items():
        if passed:
            continue
        if key == "field_length_valid":
            d = result.get("_desc_len", "?")
            n = result.get("_name_len", "?")
            md = cfg.get("max_description_chars", "1024")
            mn = cfg.get("max_name_chars", "64")
            issues.append(f"description {d}/{md} chars, name {n}/{mn} chars")
        elif key == "within_optimal_lines":
            lc  = result.get("_line_count", "?")
            lim = cfg.get("optimal_line_limit", "?")
            issues.append(f"lines {lc}/{lim} optimal")
        elif key == "under_line_limit":
            lc  = result.get("_line_count", "?")
            lim = cfg.get("hard_line_limit", "?")
            issues.append(f"lines {lc}/{lim} hard limit")
        elif key == "body_size_valid":
            cc  = result.get("_char_count", "?")
            mn  = cfg.get("min_body_chars", "?")
            mx  = cfg.get("max_body_chars", "?")
            issues.append(f"body {cc} chars, expected {mn} to {mx}")
        else:
            issues.append(STRUCTURE_LABELS.get(key, key))

    return issues


def _quality_issues(result: dict) -> list[str]:
    checks = result.get("_quality_checks", {})
    return [QUALITY_LABELS.get(k, k) for k, passed in checks.items() if not passed]
