---
name: gh-copilot-adoption-onboard
description: >
  Onboard a target repository to the GitHub Copilot Adoption Framework by
  creating standard .github folders, adding validation workflow and Copilot
  instructions, then opening a pull request.
---

# GitHub Adoption Framework - Repo Onboarding

Onboards a repository to the GitHub Copilot Adoption Framework. Checks
permissions, forks if needed, creates the standard folder structure using
`onboarding-templates.md`, prevents duplicate PRs, and opens a pull request
against the default branch. Nothing is committed directly to `main`.

## Skill Files

This skill folder contains:

- `SKILL.md`
- `onboarding-templates.md`
- `validate-copilot-agent.yml`

## When to Use

- "Onboard my repo to the GitHub Adoption Framework"
- "Onboard [repo-name] to Agent Factory"
- "Set up [repo-name] for Agent Factory"
- "Add Copilot framework files to [repo]"
- "Enable Agent Factory on my repo"
- "onboard repo"

Do not use if the repo already has `.github/agents/`, `.github/skills/`, and
`.github/instructions/` present unless the user confirms re-onboarding.

## Prerequisites

- `gh` CLI authenticated (`gh auth status`) or GitHub MCP server connected
- `onboarding-templates.md` and `validate-copilot-agent.yml` present in this skill folder

## Steps

### Step 1 - Ask for Repository Name

Ask the user:

> "Which repository would you like to onboard? Please provide the full name
> in `owner/repo` format (e.g., `my-org/my-project`)."

Validate the input matches `<owner>/<repo>` format before continuing. If
invalid, ask again.

### Step 2 - Check Permissions and Decide Workflow

```bash
TARGET_REPO="<owner>/<repo>"
REPO_NAME=$(echo $TARGET_REPO | cut -d'/' -f2)
YOUR_ACCOUNT=$(gh api user --jq '.login')

# Check viewer permission on target repo
PERMISSION=$(gh repo view $TARGET_REPO --json viewerPermission \
  --jq '.viewerPermission')

if [ "$PERMISSION" = "WRITE" ] || \
   [ "$PERMISSION" = "MAINTAIN" ] || \
   [ "$PERMISSION" = "ADMIN" ]; then
  WORK_REPO=$TARGET_REPO
  USE_FORK=false
else
  # Fork the target repo to authenticated account
  gh repo fork $TARGET_REPO --clone=false
  WORK_REPO="$YOUR_ACCOUNT/$REPO_NAME"
  USE_FORK=true
fi
```

### Step 3 - Clone and Create Branch

```bash
gh repo clone $WORK_REPO /tmp/$REPO_NAME-onboarding
cd /tmp/$REPO_NAME-onboarding
git checkout -b feat/gh-copilot-adoption-onboard
```

If the branch already exists, use `feat/gh-copilot-adoption-onboard-YYYYMMDD`.

### Step 4 - Create Framework Folders and Files

```bash
mkdir -p /tmp/$REPO_NAME-onboarding/.github/agents
mkdir -p /tmp/$REPO_NAME-onboarding/.github/skills/sample
mkdir -p /tmp/$REPO_NAME-onboarding/.github/instructions
mkdir -p /tmp/$REPO_NAME-onboarding/.github/workflows
```

Read `onboarding-templates.md` from this skill folder. For each `## TARGET:`
section, create the file at the specified target path using the section content
verbatim.

| Section in `onboarding-templates.md` | Target path |
|---|---|
| `TARGET: .github/copilot-instructions.md` | `.github/copilot-instructions.md` |
| `TARGET: .github/agents/sample.agent.md` | `.github/agents/sample.agent.md` |
| `TARGET: .github/skills/sample/SKILL.md` | `.github/skills/sample/SKILL.md` |
| `TARGET: .github/instructions/sample.instructions.md` | `.github/instructions/sample.instructions.md` |

### Step 5 - Copy the Validation Workflow File

Copy `validate-copilot-agent.yml` from this skill folder to:

```
/tmp/$REPO_NAME-onboarding/.github/workflows/validate-copilot-agent.yml
```

If `validate-copilot-agent.yml` is missing from the skill folder, stop and
report that the skill package is incomplete.

### Step 6 - Commit and Push

```bash
cd /tmp/$REPO_NAME-onboarding
git add .
git commit -m "feat: onboard repository to GitHub Adoption Framework

- Add .github/copilot-instructions.md
- Add .github/agents/sample.agent.md
- Add .github/skills/sample/SKILL.md
- Add .github/instructions/sample.instructions.md
- Add .github/workflows/validate-copilot-agent.yml"
git push origin feat/gh-copilot-adoption-onboard
```

### Step 7 - Check for Existing PR

Before creating a new PR, check if one already exists.

```bash
EXISTING_PR=$(gh pr list \
  --repo $TARGET_REPO \
  --head "feat/gh-copilot-adoption-onboard" \
  --state open \
  --json url \
  --jq '.[0].url')

if [ -n "$EXISTING_PR" ]; then
  echo "An onboarding PR already exists: $EXISTING_PR"
  echo "Please review and merge or close it before raising a new one."
  exit 0
fi
```

### Step 8 - Raise a Pull Request

```bash
if [ "$USE_FORK" = true ]; then
  HEAD="$YOUR_ACCOUNT:feat/gh-copilot-adoption-onboard"
else
  HEAD="feat/gh-copilot-adoption-onboard"
fi

gh pr create \
  --repo $TARGET_REPO \
  --title "feat: onboard to GitHub Adoption Framework" \
  --body "## Summary
Onboards this repository to the GitHub Copilot Adoption Framework.

## Changes
- \`.github/copilot-instructions.md\` - repo-level Copilot guidance
- \`.github/agents/sample.agent.md\` - example agent definition
- \`.github/skills/sample/SKILL.md\` - example skill definition
- \`.github/instructions/sample.instructions.md\` - example path-specific instructions
- \`.github/workflows/validate-copilot-agent.yml\` - framework validation on PRs

## Next Steps
- Update \`.github/copilot-instructions.md\` with project-specific conventions.
- Replace sample files in \`agents/\`, \`skills/\`, and \`instructions/\` with real definitions." \
  --base main \
  --head $HEAD
```

Share the PR URL with the user.

### Step 9 - Clean Up

```bash
rm -rf /tmp/$REPO_NAME-onboarding
```

## Error Handling

| Situation | Resolution |
|---|---|
| Target repo not found | Verify `<owner>/<repo>` format; confirm repo exists. |
| No write access | Fork workflow is triggered automatically. |
| Fork fails | Check if a fork already exists; use existing fork. |
| `onboarding-templates.md` missing | Stop and report skill package is incomplete. |
| `validate-copilot-agent.yml` missing | Stop and report skill package is incomplete. |
| Branch already exists | Use `feat/gh-copilot-adoption-onboard-YYYYMMDD` as branch name. |
| PR already open | Share existing PR URL; do not create a duplicate. |
| Auth error | Run `gh auth status`; reconnect via `gh auth login`. |
| Framework files already exist | Inform user repo may already be onboarded; confirm before proceeding. |

## Security

- No hardcoded credentials. Never embed tokens, PATs, or secrets in any file.
- Use `gh` CLI or GitHub MCP only. Never use raw `curl` with inline tokens.
- PR-only. Always raise a PR; no direct commits to `main`.
- Validate input. Confirm `<owner>/<repo>` format before proceeding.
- Clean up. Always remove `/tmp/` clones after the PR is raised.
