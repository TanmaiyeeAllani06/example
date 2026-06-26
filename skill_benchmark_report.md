# GitHub Copilot Skill Benchmark Report

**Skills Evaluated:** 4

---

## Validation Criteria

| Dimension | Criteria |
|---|---|
| **Structure** | File format, filename, YAML frontmatter, required fields, desc <= 1024 chars, name <= 64 chars, body 30–15000 chars, headings, lines <= 200 optimal / 500 hard, no absolute paths, no external URLs |
| **Content Quality** | When-to-use, instructions, examples, multiple sections, no code block leaks, structured tags, no placeholder text, section dominance, no duplicate phrases, bullet word limit, description completeness, negative cases, imperative directives, gotchas/edge cases, output templates, validation loops, progressive disclosure, TOC for reference files |
| **Token Efficiency** | tiktoken cl100k_base — STRONG <= 2000 tokens, MODERATE <= 5000 tokens, WEAK > 5000 tokens |
| **Security** | Hardcoded API keys/tokens, shell tool security warnings, prompt injection patterns — PASS / FAIL |

---

## Results

| Skill | Structure | Content Quality | Token Efficiency | Security | Overall |
|---|---|---|---|---|---|
| **az-cost-optimize** | STRONG (87.5%) | WEAK (45.0%) | MODERATE (2956 tokens) | PASS | 🟡 MODERATE (60.0%) |
| **copilot-instructions-blueprint-generator** | STRONG (93.8%) | MODERATE (50.0%) | MODERATE (2981 tokens) | PASS | 🟢 STRONG (75.0%) |
| **draw-io-diagram-generator** | MODERATE (75.0%) | MODERATE (50.0%) | WEAK (5377 tokens) | PASS | 🟡 MODERATE (52.5%) |
| **github-adoption-onboarding** | STRONG (87.5%) | MODERATE (65.0%) | STRONG (1583 tokens) | PASS | 🟢 STRONG (85.0%) |

---

## Recommendations

<details>
<summary>🟡 az-cost-optimize — MODERATE (60.0%)</summary>

- Content Quality: Include a 'when to use' section with trigger scenarios, Include an examples section with usage samples, Remove raw code blocks (```python, ```json), Remove repeated phrases, each sentence should add unique value, Description must explain WHAT the skill does AND WHEN to use it, Description should specify WHEN NOT to use this skill, Instructions should use directive verbs (direct action commands like Run, Create, Verify), Include a gotchas section (documents known pitfalls and edge cases), Define output templates (expected response format), Include verification steps (self-check loops to confirm correctness), Skills over 300 lines should split details into reference files
- Token Efficiency: Reduce file size (2956 tokens, target <= 2000)

</details>

<details>
<summary>🟢 copilot-instructions-blueprint-generator — STRONG (75.0%)</summary>

- Content Quality: Include a 'when to use' section with trigger scenarios, Include an instructions section with step-by-step workflow, Include an examples section with usage samples, Remove repeated phrases, each sentence should add unique value, Description must explain WHAT the skill does AND WHEN to use it, Description should specify WHEN NOT to use this skill, Instructions should use directive verbs (direct action commands like Run, Create, Verify), Include a gotchas section (documents known pitfalls and edge cases), Define output templates (expected response format), Include verification steps (self-check loops to confirm correctness)
- Token Efficiency: Reduce file size (2981 tokens, target <= 2000)

</details>

<details>
<summary>🟡 draw-io-diagram-generator — MODERATE (52.5%)</summary>

- Structure: Body content must be between 30 and 15,000 characters, File exceeds 200-line optimal limit, Use relative paths only, no C:\ or /usr/ paths, Remove external web links (http/https URLs)
- Content Quality: Include a 'when to use' section with trigger scenarios, Include an examples section with usage samples, Remove raw code blocks (```python, ```json), Description must explain WHAT the skill does AND WHEN to use it, Description should specify WHEN NOT to use this skill, Instructions should use directive verbs (direct action commands like Run, Create, Verify), Include a gotchas section (documents known pitfalls and edge cases), Define output templates (expected response format), Include verification steps (self-check loops to confirm correctness), Skills over 300 lines should split details into reference files
- Token Efficiency: Reduce file size (5377 tokens, target <= 2000)

</details>

<details>
<summary>🟢 github-adoption-onboarding — STRONG (85.0%)</summary>

- Content Quality: Remove raw code blocks (```python, ```json), Description must explain WHAT the skill does AND WHEN to use it, Description should specify WHEN NOT to use this skill, Instructions should use directive verbs (direct action commands like Run, Create, Verify), Include a gotchas section (documents known pitfalls and edge cases), Define output templates (expected response format), Include verification steps (self-check loops to confirm correctness)

</details>

---

## Conclusion

**🟢 Ready for Adoption:** copilot-instructions-blueprint-generator, github-adoption-onboarding

**🟡 Needs Improvement:** az-cost-optimize, draw-io-diagram-generator

## CLI Validation (gh skill publish --dry-run)
```text
warning	az-cost-optimize	recommended field missing: license
warning	copilot-instructions-blueprint-generator	recommended field missing: license
warning	draw-io-diagram-generator	recommended field missing: license
warning	github-adoption-onboarding	recommended field missing: license
warning		no active tag protection rulesets found. Consider protecting tags to ensure immutable releases (Settings > Rules > Rulesets)


Dry run complete. Use without --dry-run to publish.
```
