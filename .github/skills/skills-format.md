<!-- File: .github/skills/skills-format.md -->
# Skills Format

Overview of Agent Skills [AgentSkills.io](https://agentskills.io/home)

## Files Location

| Type | Scope | Location |
| ---- | ----- | -------- |
| Skills | Workspace | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| Skills | Personal | `~/.copilot/skills/`, `~/.claude/skills/`, `~/.agents/skills/` |
| Instructions | Workspace | `.github/instructions` |
| Instructions | Personal | `~/.copilot/instructions`, `~/.claude/rules` |

## Simple SKILL.md

```markdown
<!-- File: .github/skills/skill-name/SKILL.md -->
---
name: skill-name
description: Description of what the skill does and when to use it
---

# Skill Instructions

Your detailed instructions, guidelines, and examples go here...
```

## Header fields for SKILL.md

Fields for header formatted as YAML (required):

| Field | Required | Description |
| ----- | -------- | ----------- |
| name | Yes | A unique identifier for the skill. Must be lowercase, using hyphens for spaces (for example, webapp-testing). Must match the parent directory name. Maximum 64 characters. |
| description | Yes | A description of what the skill does and when to use it. Be specific about both capabilities and use cases to help Copilot decide when to load the skill. Maximum 1024 characters. |
| argument-hint | No | Hint text shown in the chat input field when the skill is invoked as a slash command. Helps users understand what additional information to provide (for example, [test file] [options]). |
| license | No | License name or reference to a bundled license file. |
| compatibility | No | Max 500 characters. Indicates environment requirements (intended product, system packages, network access, etc.). |
| metadata | No | Arbitrary key-value mapping for additional metadata. |
| allowed-tools | No | Space-delimited list of pre-approved tools the skill may use. (Experimental) |
| user-invocable | No | Controls whether the skill appears as a slash command in the chat menu. Defaults to true. Set to false to hide the skill from the / menu while still allowing the agent to load it automatically. |
| disable-model-invocation | No | Controls whether the agent can automatically load the skill based on relevance. Defaults to false. Set to true to require manual invocation through the / slash command only. |

## Body for SKILL.md

The skill body contains the instructions, guidelines, and examples that Copilot should follow when using this skill. Write clear, specific instructions that describe:

- What the skill helps accomplish
- When to use the skill
- Step-by-step procedures to follow
- Examples of the expected input and output
- References to any included scripts or resources

You can reference files within the skill directory using relative paths. For example, to reference a script in your skill directory, use [test script](./test-template.js)

## Folder structure for SKILL.md

Required folder structure
The skill directory must follow this structure:

```text
.github/
├── instructions/
|   ├── frontend/
|   |   ├── react.instructions.md
|   |   └── accessibility.instructions.md
|   ├── backend/
|   |   └── api-design.instructions.md
|   ├── testing/
|   |   └── unit-tests.instructions.md
|   └── ...
├── skills/
    ├── skill-1-name/         # Required: Directory name match the `name` field in SKILL.md
    |   ├── SKILL.md          # Required: metadata + instructions
    |   ├── scripts/          # Optional: executable code
    |   ├── references/       # Optional: documentation
    |   ├── assets/           # Optional: templates, resources
    |   └── ...               # Any additional files or directories
    ├── skill-2-name/
    |   ├── SKILL.md
    |   └── ...
    └── ...
```
