import html
import re
from pathlib import Path

STRUCTURE_LABELS = {
    "file_is_markdown": "File must be a Markdown (.md) file",
    "filename_kebab_case": "Filename must use lowercase kebab-case convention",
    "yaml_frontmatter_exists": "YAML frontmatter block is missing",
    "required_fields_present": "Required fields 'name' and 'description' must be present",
    "field_length_valid": "Field lengths exceed configured limits",
    "body_size_valid": "File content size is outside the allowed range",
    "has_headings": "Add section headings",
    "under_line_limit": "File exceeds the hard line limit",
    "within_optimal_lines": "File exceeds the optimal line limit",
    "no_absolute_paths": "Remove absolute file paths from content",
    "no_external_urls": "Remove external URLs from content",
}

QUALITY_LABELS = {
    "has_when_to_use": "Add a 'When to Use' section",
    "has_instructions": "Add an instructions or workflow section",
    "has_examples": "Add usage examples",
    "has_multiple_sections": "Add multiple sections using headings",
    "no_code_block_leaks": "Remove forbidden code block leaks",
    "has_structured_tags": "Add structured XML-style tags for better Copilot parsing",
    "no_placeholder_text": "Remove placeholder text",
    "has_meaningful_length": "File content is too short",
    "section_dominance_met": "Increase structured section coverage",
    "no_duplicate_phrases": "Remove repeated phrases - content appears redundant",
    "bullets_within_limit": "Shorten long bullet points",
}


def render_skills_evaluation_dashboard(results, output_path: Path, config: dict | None = None, dryrun_log: str = "") -> None:
    """Render an HTML dashboard from skill benchmark results."""
    output_path = Path(output_path)
    config = config or {}

    strong = [r for r in results if r["overall"].startswith("STRONG")]
    moderate = [r for r in results if r["overall"].startswith("MODERATE")]
    weak = [r for r in results if r["overall"].startswith("WEAK")]
    security_failures = [r for r in results if not r.get("_security_ok", False)]

    total = len(results)
    avg_overall = round(sum(_extract_pct(r["overall"]) for r in results) / total, 1) if total else 0.0
    strong_pct = round((len(strong) / total) * 100, 1) if total else 0.0
    moderate_pct = round((len(moderate) / total) * 100, 1) if total else 0.0
    weak_pct = round((len(weak) / total) * 100, 1) if total else 0.0
    security_pass_pct = round(((total - len(security_failures)) / total) * 100, 1) if total else 0.0

    rows = []
    issue_cards = []

    for result in sorted(results, key=lambda item: _extract_pct(item["overall"]), reverse=True):
        name = html.escape(result["name"])
        struct_pct = _extract_pct(result["structure"])
        quality_pct = _extract_pct(result["content_quality"])
        token_pct = _token_visual_score(result)
        security_pct = 100 if result.get("_security_ok", False) else 0
        security_label = "PASS" if result.get("_security_ok", False) else "FAIL"

        rows.append(f"""
        <tr>
          <td class="skill-name">{name}</td>
          <td><span class="pill {_tier_class(result['overall'])}">{html.escape(result['overall'])}</span></td>
          <td>{_dimension_cell(struct_pct, result['structure'])}</td>
          <td>{_dimension_cell(quality_pct, result['content_quality'])}</td>
          <td>{_dimension_cell(token_pct, result['token_efficiency'])}</td>
          <td>{_dimension_cell(security_pct, security_label)}</td>
        </tr>
        """)

        grouped_issues = _group_recommendations(result, config)
        if grouped_issues:
            issue_cards.append(_issue_card(result, grouped_issues))

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
        </article>
        """)
        
    # Build the CLI Output HTML block
    dryrun_html = ""
    if dryrun_log:
        dryrun_html = f"""
  <section class="panel" style="border-left: 5px solid var(--green);">
    <div class="panel-head" style="margin-bottom: 8px;">
      <h2 style="color: var(--ink); font-size: 18px;">1. Primary Validation (GitHub CLI)</h2>
    </div>
    <div style="background: var(--ink); color: #00ff00; padding: 14px; border-radius: 8px; overflow-x: auto; font-family: Consolas, monospace; font-size: 13px; line-height: 1.4;">
      <pre style="margin: 0;">{html.escape(dryrun_log.strip())}</pre>
    </div>
  </section>
  <h2 style="margin-top: 16px; margin-bottom: -6px; padding-left: 4px; color: var(--ink); font-size: 20px;">2. Deep Semantic Evaluation (Our Framework)</h2>
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
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page);
    color: var(--ink);
    font-family: "Segoe UI", Aptos, Arial, sans-serif;
  }}
  main {{
    width: calc(100% - 36px);
    margin: 18px auto 32px;
  }}
  header, .panel, .summary-strip, .issue-card {{
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 10px;
    box-shadow: 0 10px 24px rgba(16, 24, 40, 0.08);
  }}
  header {{
    padding: 24px 28px;
  }}
  h1 {{
    margin: 0;
    font-size: 36px;
    letter-spacing: 0;
  }}
  .subtitle {{
    max-width: 900px;
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 16px;
  }}
  .summary-strip {{
    margin-top: 14px;
    padding: 16px;
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 12px;
  }}
  .rail-metric {{
    display: grid;
    grid-template-columns: 96px minmax(0, 1fr);
    gap: 14px;
    align-items: center;
    padding: 14px;
    border: 1px solid #e3eaf2;
    border-radius: 8px;
    background: #fbfdff;
  }}
  .ring {{
    width: 88px;
    height: 88px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    background: conic-gradient(var(--color) calc(var(--value) * 1%), #e5edf5 0);
    position: relative;
  }}
  .ring::after {{
    content: "";
    position: absolute;
    inset: 12px;
    background: #ffffff;
    border-radius: 50%;
  }}
  .ring span {{
    position: relative;
    z-index: 1;
    font-size: 16px;
    font-weight: 850;
  }}
  .rail-metric strong {{
    display: block;
    font-size: 14px;
  }}
  .rail-metric small {{
    display: block;
    margin-top: 3px;
    color: var(--muted);
  }}
  .panel {{
    padding: 22px;
    margin-top: 16px;
  }}
  .panel-head {{
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
    margin-bottom: 16px;
  }}
  h2 {{
    margin: 0;
    font-size: 23px;
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    color: var(--muted);
    font-size: 13px;
  }}
  .dot {{
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 5px;
  }}
  .stacked {{
    display: flex;
    height: 24px;
    overflow: hidden;
    border-radius: 999px;
    background: #e5edf5;
  }}
  .seg-strong {{ width: {strong_pct}%; background: var(--green); }}
  .seg-moderate {{ width: {moderate_pct}%; background: var(--amber); }}
  .seg-weak {{ width: {weak_pct}%; background: var(--red); }}
  table {{
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }}
  col.skill {{ width: 24%; }}
  col.overall {{ width: 14%; }}
  col.metric {{ width: 15.5%; }}
  th, td {{
    padding: 14px 10px;
    border-bottom: 1px solid #e3eaf2;
    text-align: left;
    vertical-align: middle;
  }}
  th {{
    color: var(--muted);
    font-size: 12px;
    text-transform: uppercase;
  }}
  .skill-name {{
    font-weight: 850;
    overflow-wrap: anywhere;
  }}
  .pill {{
    display: inline-flex;
    align-items: center;
    min-height: 26px;
    padding: 5px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 850;
    white-space: nowrap;
  }}
  .strong {{ background: var(--green-soft); color: var(--green); }}
  .moderate {{ background: var(--amber-soft); color: #8c5f00; }}
  .weak {{ background: var(--red-soft); color: #9c342b; }}
  .dimension-cell {{
    display: grid;
    gap: 6px;
    align-items: center;
  }}
  .mini-bar {{
    width: 100%;
    height: 11px;
    background: #e5edf5;
    border-radius: 999px;
    overflow: hidden;
  }}
  .mini-bar span {{
    display: block;
    height: 100%;
    background: var(--blue);
  }}
  .dimension-cell > span {{
    min-height: 18px;
    color: #364a63;
    font-size: 13px;
    line-height: 1.35;
  }}
  .issue-list {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
  }}
  .issue-card {{
    padding: 16px;
  }}
  .issue-head {{
    display: flex;
    justify-content: space-between;
    gap: 10px;
    align-items: center;
    margin-bottom: 14px;
  }}
  .issue-head strong {{
    overflow-wrap: anywhere;
  }}
  .issue-section {{
    display: grid;
    grid-template-columns: 132px minmax(0, 1fr);
    gap: 10px;
    padding: 10px 0;
    border-top: 1px solid #e8eef5;
  }}
  .issue-category {{
    color: var(--blue);
    font-size: 12px;
    font-weight: 850;
    text-transform: uppercase;
  }}
  .issue-items {{
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }}
  .issue-items span {{
    padding: 6px 8px;
    border-radius: 7px;
    background: var(--blue-soft);
    color: #244763;
    font-size: 12px;
    font-weight: 650;
    cursor: default;
  }}
  @media (max-width: 1180px) {{
    .summary-strip {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
    .issue-list {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }}
  }}
  @media (max-width: 760px) {{
    main {{
      width: calc(100% - 20px);
    }}
    h1 {{
      font-size: 30px;
    }}
    .summary-strip, .issue-list {{
      grid-template-columns: 1fr;
    }}
    table {{
      display: block;
      overflow-x: auto;
      min-width: 980px;
    }}
  }}
</style>
</head>
<body>
<main>
  <header>
    <h1>GitHub Copilot Skill Benchmark Dashboard</h1>
    <p class="subtitle">Visual summary of Structure, Content Quality, Token Efficiency, Security, and overall readiness.</p>
  </header>

  {dryrun_html}

  <section class="summary-strip">
    {_ring("Avg overall", avg_overall, f"{total} skills evaluated", "var(--blue)")}
    {_ring("Strong", strong_pct, f"{len(strong)} skills", "var(--green)")}
    {_ring("Moderate", moderate_pct, f"{len(moderate)} skills", "var(--amber)")}
    {_ring("Weak", weak_pct, f"{len(weak)} skills", "var(--red)")}
    {_ring("Security pass", security_pass_pct, f"{len(security_failures)} failures", "var(--green)")}
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
    <div class="panel-head">
      <h2>Benchmark Matrix</h2>
    </div>
    <table>
      <colgroup>
        <col class="skill">
        <col class="overall">
        <col class="metric">
        <col class="metric">
        <col class="metric">
        <col class="metric">
      </colgroup>
      <thead>
        <tr>
          <th>Skill</th>
          <th>Overall</th>
          <th>Structure</th>
          <th>Content Quality</th>
          <th>Token Efficiency</th>
          <th>Security</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </section>

  <section class="panel">
    <div class="panel-head">
      <h2>Improvement Focus</h2>
    </div>
    <div class="issue-list">{''.join(issue_cards)}</div>
  </section>
</main>
</body>
</html>"""

    output_path.write_text(html_doc, encoding="utf-8")


def _extract_pct(label: str) -> float:
    match = re.search(r"\(([\d.]+)%\)", label)
    return float(match.group(1)) if match else 0.0


def _tier_class(label: str) -> str:
    if label.startswith("STRONG") or label == "PASS":
        return "strong"
    if label.startswith("MODERATE"):
        return "moderate"
    return "weak"


def _bar_width(value: float) -> float:
    return max(0.0, min(100.0, value))


def _token_visual_score(result: dict) -> int:
    token_tier = result.get("_token_tier")
    if token_tier == "STRONG":
        return 100
    if token_tier == "MODERATE":
        return 65
    return 30


def _dimension_cell(score: float, label: str) -> str:
    return f"""
    <div class="dimension-cell">
      <div class="mini-bar"><span style="width:{_bar_width(score)}%"></span></div>
      <span>{html.escape(label)}</span>
    </div>
    """


def _ring(label: str, value: float, note: str, color: str) -> str:
    return f"""
    <div class="rail-metric">
      <div class="ring" style="--value:{_bar_width(value)}; --color:{color};">
        <span>{value:.1f}%</span>
      </div>
      <div>
        <strong>{html.escape(label)}</strong>
        <small>{html.escape(note)}</small>
      </div>
    </div>
    """


def _issue_card(result: dict, grouped_issues: list[tuple[str, list[str]]]) -> str:
    sections = []
    for category, parts in grouped_issues:
        visible_parts = parts[:5]
        extra = len(parts) - len(visible_parts)
        sections.append(f"""
        <div class="issue-section">
          <div class="issue-category">{html.escape(category)}</div>
          <div class="issue-items">
            {''.join(f'<span>{html.escape(part)}</span>' for part in visible_parts)}
            {f'<span>+{extra} more</span>' if extra > 0 else ''}
          </div>
        </div>
        """)

    return f"""
    <article class="issue-card">
      <div class="issue-head">
        <strong>{html.escape(result["name"])}</strong>
        <span class="pill {_tier_class(result['overall'])}">{html.escape(result['overall'])}</span>
      </div>
      {''.join(sections)}
    </article>
    """


def _group_recommendations(result: dict, config: dict) -> list[tuple[str, list[str]]]:
    grouped = []

    if not result.get("_security_ok", False):
        grouped.append(("Security", [f"Remove hardcoded credentials: {', '.join(result.get('_secrets', []))}"]))

    structure_issues = _structure_issues(result, config)
    if structure_issues:
        grouped.append(("Structure", structure_issues))

    quality_issues = _quality_issues(result)
    if quality_issues:
        grouped.append(("Content Quality", quality_issues))

    if result.get("_token_tier") != "STRONG":
        token_limit = config.get("token_thresholds", {}).get("strong_max", "configured")
        grouped.append(("Token Efficiency", [f"{result.get('_token_count', 0)}/{token_limit} tokens for STRONG"]))

    return [(category, parts) for category, parts in grouped if parts]


def _structure_issues(result: dict, config: dict) -> list[str]:
    cfg = config.get("structure", {})
    checks = result.get("_struct_checks", {})
    issues = []

    for key, passed in checks.items():
        if passed:
            continue
        if key == "field_length_valid" and "_desc_len" in result:
            issues.append(
                f"description {result.get('_desc_len')}/{cfg.get('max_description_chars', 'limit')} chars, "
                f"name {result.get('_name_len')}/{cfg.get('max_name_chars', 'limit')} chars"
            )
        elif key == "within_optimal_lines" and "_line_count" in result:
            issues.append(f"lines {result.get('_line_count')}/{cfg.get('optimal_line_limit', 'limit')} optimal")
        elif key == "under_line_limit" and "_line_count" in result:
            issues.append(f"lines {result.get('_line_count')}/{cfg.get('hard_line_limit', 'limit')} hard limit")
        elif key == "body_size_valid" and "_char_count" in result:
            issues.append(
                f"body {result.get('_char_count')} chars, expected "
                f"{cfg.get('min_body_chars', 'min')}-{cfg.get('max_body_chars', 'max')}"
            )
        else:
            issues.append(STRUCTURE_LABELS.get(key, key))

    return issues


def _quality_issues(result: dict) -> list[str]:
    checks = result.get("_quality_checks", {})
    return [QUALITY_LABELS.get(key, key) for key, passed in checks.items() if not passed]
