# Onboarding Templates

Source file for the `gh-copilot-adoption-onboard` skill.
Read this file during Step 3. For each `## TARGET:` section, create the file
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

## TARGET: .github/agents/README.md

~~~markdown
# Agents

This folder contains named agent definitions for the GitHub Copilot Adoption Framework.

## What Is an Agent

An agent is a scoped role definition that tells GitHub Copilot how to behave when
assigned a specific task. Each agent references one or more skills and defines clear
responsibilities, rules, and verification criteria.

## File Naming

Agent files use the `.agent.md` extension:

```
.github/agents/<agent-name>.agent.md
```

## Frontmatter Schema

Every agent file must include:

```yaml
---
name: agent-name
description: >
  What this agent does and when to use it.
skills:
  - skill-name
---
```

## Agent Structure

Each agent file must define:

- **Primary Goal** — the single main outcome this agent is responsible for
- **Required Inputs** — what information the agent needs before acting
- **Responsibilities** — each action the agent performs, specific and verifiable
- **Rules** — constraints and guardrails
- **Verification** — how the agent confirms its work is complete

## Conventions

- One agent per file.
- Agent names must be unique across this folder.
- Agents must not hardcode credentials, tokens, or secrets.
- Agents must raise pull requests. Never commit directly to `main`.
~~~

---

## TARGET: .github/skills/README.md

~~~markdown
# Skills

This folder contains reusable skill definitions for the GitHub Copilot Adoption Framework.

## What Is a Skill

A skill is a packaged, step-by-step workflow that an agent can follow to complete a
specific task. Skills are self-contained: they include all steps, error handling, and
security rules needed to complete the task without relying on context outside the skill file.

## Folder Structure

Each skill lives in its own named subfolder containing a `SKILL.md`:

```
.github/skills/<skill-name>/SKILL.md
```

A skill folder may also include supporting files the skill depends on.

## Frontmatter Schema

Every `SKILL.md` must include:

```yaml
---
name: skill-name
description: >
  What this skill does and when to use it.
---
```

## Skill Structure

Each `SKILL.md` must define:

- **When to Use** — trigger phrases and conditions where this skill applies
- **Prerequisites** — what must be true before the skill can run
- **Steps** — numbered, sequential steps with commands where applicable
- **Error Handling** — a table of known failure cases and their resolutions
- **Security** — constraints specific to this skill

## Conventions

- One skill per subfolder.
- Skill names must be unique across this folder.
- Skills must not hardcode credentials, tokens, or secrets.
- Keep steps concrete and verifiable.
- Supporting files belong inside the skill's subfolder, not at the root of `skills/`.
~~~

---

## TARGET: .github/instructions/framework.instructions.md

~~~markdown
---
applyTo: ".github/**"
---

# Framework Instructions

These instructions apply to all files under `.github/` in this repository.

## Agents

Files in `.github/agents/` define named Copilot agents.

- Use the `.agent.md` extension for all agent definition files.
- Required frontmatter: `name`, `description`, `skills`.
- Each agent must define: Primary Goal, Required Inputs, Responsibilities, Rules, Verification.
- Agents must not commit directly to `main`.
- Agents must not hardcode credentials, tokens, or secrets.

## Skills

Files in `.github/skills/` define reusable skill packages.

- Each skill lives in its own named subfolder: `.github/skills/<skill-name>/SKILL.md`.
- Required frontmatter: `name`, `description`.
- Each skill must define: When to Use, Prerequisites, Steps, Error Handling, Security.
- Supporting files belong inside the skill's subfolder, not at the root of `skills/`.

## Instructions

Files in `.github/instructions/` define path-specific Copilot guidance.

- Required frontmatter: `applyTo` targeting one or more file glob patterns.
- Instructions apply only when Copilot is working with files matching the `applyTo` pattern.
- Keep instructions concise. Avoid duplicating content already in `copilot-instructions.md`.

## Workflows

Files in `.github/workflows/` are GitHub Actions workflows.

- Do not modify `validate-copilot-agent.yml` unless the upstream framework is updated.
- All workflow changes go through pull requests against `main`.

## General Conventions

- All `.github/` changes go through pull requests. No direct commits to `main`.
- No hardcoded credentials, tokens, or secrets in any file.
- Avoid redundancy across agents, skills, instructions, and `copilot-instructions.md`.
~~~
