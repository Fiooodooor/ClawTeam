<!-- File: .github/instructions/instructions-format.md -->
# Instructions Format

## Files Location

| Type | Scope | Location |
| ---- | ----- | -------- |
| Skills | Workspace | `.github/skills/`, `.claude/skills/`, `.agents/skills/` |
| Skills | Personal | `~/.copilot/skills/`, `~/.claude/skills/`, `~/.agents/skills/` |
| Instructions | Workspace | `.github/instructions/` |
| Instructions | Personal | `~/.copilot/instructions/`, `~/.claude/rules/` |
| Agents | Workspace | `.github/agents/`, `.claude/agents/` |
| Agents | Personal | `~/.copilot/agents/` |

## Instruction File Format

Generic: `.github/instructions/*.instructions.md`

VS Code searches these folders recursively, so you can organize instructions files in subdirectories. For example, you can group instructions by team, language, or module:

```markdown
<!-- File: .github/copilot-instructions.md -->
---
applyTo: "**"
---
# Project general coding standards

## Naming Conventions
- Use PascalCase for component names, interfaces, and type aliases
- Use camelCase for variables, functions, and methods
- Prefix private class members with underscore (_)
- Use ALL_CAPS for constants

## Error Handling
- Use try/catch blocks for async operations
- Implement proper error boundaries in React components
- Always log errors with contextual information
```

```markdown
<!-- File: .github/instructions/coding/python.instructions.md -->
---
name: 'Python Standards'
description: 'Coding conventions for Python files'
applyTo: '**/*.py'
---
# Python coding standards
- Follow the PEP 8 style guide.
- Use type hints for all function signatures.
- Write docstrings for public functions.
- Use 4 spaces for indentation.
```

## Instructions file structure

```text
.github/
├── copilot-instructions.md
├── instructions/
|   ├── frontend/
|   |   ├── react.instructions.md
|   |   └── accessibility.instructions.md
|   ├── backend/
|   |   └── api-design.instructions.md
|   ├── testing/
|   |   └── unit-tests.instructions.md
|   └── ...
└── skills/
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
