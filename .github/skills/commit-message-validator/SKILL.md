---
name: commit-message-validator
description: "Validate and enforce standardized commit message formatting with subsystem prefixes, imperative mood, mandatory body, and metadata extraction (HSD IDs, TFS IDs, issue tracker references). Use when: reviewing commit messages, writing commit messages, configuring commit-msg hooks, or enforcing team commit standards."
argument-hint: "commit message text or git log output to validate"
---

# Commit Message Validator

Validates commit messages against the project's standardized format and suggests corrections.

## Source

Based on: `tools/scripts/commit_message_format/COMMIT_MESSAGE_FORMAT.md`

## When to Use

- Writing or reviewing commit messages
- Setting up pre-commit or commit-msg git hooks
- Enforcing commit message standards in CI pipelines
- Extracting metadata (HSD IDs, TFS IDs) from commit history

## Commit Message Format Rules

### Structure

```
<subsystem/component>: <description>

<body explaining what and why>

<optional footer with metadata>
```

### Rules

1. **Subject line** (mandatory):
   - Format: `Module: change description`
   - Imperative mood: "Add", "Fix", "Remove" (NOT "Added", "Fixed", "Removed")
   - No period at the end
   - Each line < 75 characters

2. **Body** (mandatory):
   - Separated from subject by a blank line
   - Explains **what** and **why**, not how
   - References requirements, specs, or documentation when applicable

3. **Footer** (optional):
   - `Co-authored-by: Name <email@example.com>`
   - `Fixes: <commit-hash> ("<commit-title>")`
   - `<HSD_ID: number>`
   - `<issue tracker ID>`
   - `<TFS ID>`
   - `Reviewed-by: Name <email@example.com>`

### Common Prefixes

`Reset_handler:`, `HIF:`, `Database:`, `Debug:`, `Config:`, `Test:`, `Doc:`, `Build:`

## Validation Procedure

### Step 1 — Parse the message

Split into subject, body, and footer sections separated by blank lines.

### Step 2 — Validate subject

```python
import re

def validate_subject(subject):
    errors = []
    # Must have subsystem prefix
    if not re.match(r'^[A-Za-z_-]+:', subject):
        errors.append("Missing subsystem prefix (e.g., 'Module: description')")
    # No trailing period
    if subject.endswith('.'):
        errors.append("Subject must not end with a period")
    # Imperative mood check (common past-tense words)
    past_tense = ['added', 'fixed', 'removed', 'changed', 'updated', 'implemented']
    first_word_after_prefix = subject.split(':', 1)[-1].strip().split()[0].lower() if ':' in subject else subject.split()[0].lower()
    if first_word_after_prefix in past_tense:
        errors.append(f"Use imperative mood: '{first_word_after_prefix}' → use present tense")
    # Line length
    if len(subject) > 75:
        errors.append(f"Subject is {len(subject)} chars; max 75")
    return errors
```

### Step 3 — Validate body

```python
def validate_body(body):
    errors = []
    if not body or not body.strip():
        errors.append("Body is mandatory — explain what and why")
    for i, line in enumerate(body.split('\n')):
        if len(line) > 75:
            errors.append(f"Body line {i+1} is {len(line)} chars; max 75")
    return errors
```

### Step 4 — Extract metadata

```python
def extract_metadata(message):
    metadata = {}
    hsd_ids = re.findall(r'<HSD_ID:\s*(\d+)>', message)
    tfs_ids = re.findall(r'<TFS[_ ]ID:\s*(\d+)>', message, re.IGNORECASE)
    fixes = re.findall(r'Fixes:\s*([a-f0-9]+)\s*\("([^"]+)"\)', message)
    coauthors = re.findall(r'Co-authored-by:\s*(.+)', message)
    metadata['hsd_ids'] = hsd_ids
    metadata['tfs_ids'] = tfs_ids
    metadata['fixes'] = fixes
    metadata['co_authors'] = coauthors
    return metadata
```

## Good Example

```
Reset_handler: fix IMCR flow ordering

Reorder IMCR flow operations to meet hardware timing requirements.
Previous ordering caused synchronization issues during reset sequence.

Fixes: a1b2c3d4 ("Reset_handler: add IMCR flow support")
<HSD_ID: 1380004264>
```

## Bad Example

```
Fixed bug in reset handler
```

Issues: Past tense, no module prefix, no body.
