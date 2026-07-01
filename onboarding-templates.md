# Onboarding Templates

Source file for the `gh-copilot-adoption-onboard` skill.
Read this file during Step 4. For each `## TARGET:` section, create the file
at the specified target path in the cloned repository using the section
content verbatim.

---

## TARGET: .github/copilot-instructions.md

~~~markdown
# Copilot Instructions

This repository follows the GitHub Copilot Adoption Framework.

## Project Context

<!-- Tech stack, app domain, and target environment -->

## Coding Conventions

- Match existing code style, naming, and patterns in this repository
- Use strict typing where the language supports it
- Wrap external/async calls in error handling; never swallow errors

## Architecture

<!-- Folder structure, state management, and data flow conventions -->

## Testing

<!-- Test framework, coverage expectations, and naming conventions -->

## Prohibited Practices

- No hardcoded credentials, tokens, or secrets
- No deprecated APIs or patterns
- If a library or API is unfamiliar, ask rather than guess

## Framework Structure

- `.github/agents/` - agent definitions
- `.github/skills/` - reusable skills
- `.github/instructions/` - path-specific instructions (`applyTo`)
- `.github/workflows/` - automation workflows
~~~

---

## TARGET: .github/agents/sample.agent.md

~~~markdown
---
name: sample-agent
description: >
  Replace with your agent's purpose and when to use it.
skills:
  - sample-skill
---

# Sample Agent

Replace this with your agent name. Use this agent when a user asks to
[describe the task or workflow this agent handles].

## Primary Goal

[The single main outcome this agent is responsible for.]

## Required Inputs

- [Required input — e.g., repository in `owner/repo` format]

If any required input is missing, ask the user before taking action.

## Responsibilities

- [Action one this agent performs]
- [Action two this agent performs]

## Rules

- Do not commit directly to `main`.
- Do not hardcode credentials, tokens, or secrets.
- Stop and report clearly if any required input is missing.

## Verification

```bash
test -f [expected output file]
```
~~~

---

## TARGET: .github/skills/sample/SKILL.md

~~~markdown
---
name: sample-skill
description: >
  Replace with your skill's purpose and when to use it.
---

# Sample Skill

Replace this with your skill name. [What this skill does in one sentence.]

## When to Use

- "[Trigger phrase that invokes this skill]"
- "[Another trigger phrase]"

Do not use if [describe when this skill should NOT be used].

## Prerequisites

- `gh` CLI authenticated or GitHub MCP server connected
- [Any other prerequisites]

## Steps

### Step 1 - [Step Name]

[What this step does.]

```bash
# Replace with real commands
echo "step 1"
```

### Step 2 - [Step Name]

[What this step does.]

```bash
# Replace with real commands
echo "step 2"
```

## Error Handling

| Situation | Resolution |
|---|---|
| [Error case] | [How to handle it] |
| Auth error | Run `gh auth status`; reconnect via `gh auth login`. |

## Security

- No hardcoded credentials, tokens, or secrets.
- Validate all inputs before use.
~~~

---

## TARGET: .github/instructions/sample.instructions.md

~~~markdown
---
applyTo: "src/**"
---

# Sample Instructions

Replace `applyTo` with the file pattern these instructions should apply to.
Examples:
- `"src/**"` — all source files
- `"**/*.py"` — all Python files
- `"**/*.ts"` — all TypeScript files

## Conventions

- [Convention one for files matching the applyTo pattern]
- [Convention two]

## Prohibited Practices

- [What not to do in files matching this pattern]
~~~
