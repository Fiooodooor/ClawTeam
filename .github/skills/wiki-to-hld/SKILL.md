---
name: wiki-to-hld
description: >
  Convert an Intel Confluence wiki page into a firmware High-Level Design (HLD)
  markdown document that complies with the IMC repository HLD and markdown style
  guidelines. Use this skill when a user provides a wiki URL (or page title /
  space key) and asks to create or draft an HLD document from it.
argument-hint: "<wiki-url-or-page-title>"
---

# Wiki-to-HLD Conversion

This skill converts an Intel Confluence wiki page into a firmware HLD markdown
file that follows the IMC repository standards defined in:

- `hld-documents.instructions.md` — HLD structure, sections, and content rules
- `markdown-style.instructions.md` — markdown formatting conventions
- `docs/hld/fw_feature_hld_template.md` — the canonical HLD template

## When to Use

- User provides a Confluence wiki URL or page title and asks for an HLD
- User asks to "convert", "reformat", or "draft" an HLD from a wiki page
- User wants to migrate design documentation from Confluence into the repo

## Prerequisites

| Requirement | Details |
|-------------|---------|
| **intel-wiki MCP** | Must be configured and running (see `mcp-setup` skill) |
| **Credentials** | Confluence PAT stored in `~/.netrc` |

## Troubleshooting

### intel-wiki MCP server not available

If the `intel-wiki` MCP tools fail with "MCP server could not be started" or
the `confluence_*` tools are not listed in the available tool set:

1. **Run the setup script** from the repository:
   ```bash
   cd tools/copilot-extensions/
   bash setup.sh --mcp-intel-wiki
   ```
   This installs the server to `~/.local/share/copilot-extensions/mcp/intel-wiki/`,
   prompts for a Confluence PAT, and updates `.vscode/mcp.json`.
2. **Reload VS Code** after the script completes (`Ctrl+Shift+P` →
   *Developer: Reload Window*).
3. **Verify** the MCP server appears in Copilot Chat's tool list — look for
   tools prefixed with `mcp_intel-wiki_confluence_`.

If the server was already installed but still fails:

| Symptom | Fix |
|---------|-----|
| Authentication error / 401 | PAT expired — regenerate at *wiki.ith.intel.com → Profile → Personal Access Tokens*, then re-run `setup.sh --mcp-intel-wiki` and choose to override the existing PAT |
| Connection timeout | Check Intel network / VPN connectivity; the server connects directly to `wiki.ith.intel.com` (no proxy needed for intranet) |
| `node` not found | Install Node.js v18+ (`sudo dnf install -y nodejs npm` or equivalent) |
| Server starts but tools missing | Ensure `.vscode/mcp.json` has the `"intel-wiki"` entry pointing to `~/.local/share/copilot-extensions/mcp/intel-wiki/server.js` |

For full MCP setup details see the `mcp-setup` skill or
`tools/copilot-extensions/setup.sh --help`.

## Conversion Procedure

Follow these steps **in order**. Do not skip any step.

### Step 1 — Fetch the wiki page

Use the `intel-wiki` MCP tools to retrieve the page content and attachments.

1. **Parse the URL** to extract `spaceKey` and `title` (or `pageId`).
   - URL pattern: `wiki.ith.intel.com/pages/viewpage.action?spaceKey=X&title=Y`
   - URL pattern: `wiki.ith.intel.com/pages/viewpage.action?pageId=NNN`
2. **Fetch page content** using `confluence_get_page`:
   ```
   confluence_get_page(spaceKey=..., title=...)
   # or
   confluence_get_page(pageId=...)
   ```
3. **List attachments** using `confluence_get_attachments`:
   ```
   confluence_get_attachments(pageId=<id from step 2>)
   ```
   Record each attachment's `id`, `title` (filename), and `mediaType`.

### Step 2 — Download images

If any attachments are images (`image/png`, `image/jpeg`, `image/svg+xml`,
etc.):

1. Determine the HLD output path (see [File Naming](#file-naming) below) and
   derive the **images directory** name — it is the HLD filename without the
   `.md` extension.
   - Example: HLD at `docs/hld/my_module/fw_hld_my_feature.md`
     → images in `docs/hld/my_module/fw_hld_my_feature/`
2. Download all image attachments using `confluence_download_all_attachments`:
   ```
   confluence_download_all_attachments(pageId=..., outputDir=<images_directory>)
   ```
3. Note each downloaded filename — you will reference them as placeholders.

### Step 3 — Analyze the wiki content

Read the raw Confluence storage-format HTML returned in the page body.

1. Identify the logical sections of the wiki page (headings, tables, lists,
   code blocks, diagrams).
2. Map each wiki section to the closest matching HLD template section (see
   [Section Mapping](#section-mapping) below).
3. Identify any content that does not fit the HLD template — you will place it
   in an appropriate appendix or note it for the author.

### Step 4 — Produce the HLD markdown

Generate a markdown file that:

1. **Starts with YAML frontmatter** — populate `template_version`, `feature_category`,
   `keywords`, `target_products`, and `target_fw_modules` using information
   inferred from the wiki page. If a field cannot be determined, use a
   `[placeholder]` and mark the document status as `Draft`.
2. **Follows the template structure exactly** — use the section hierarchy from
   `docs/hld/fw_feature_hld_template.md`. Do not reorder, skip, or invent
   top-level sections.
3. **Fills mandatory sections** with content adapted from the wiki page.
   Rewrite for clarity and technical precision following the HLD writing
   standards (present tense, active voice, no ambiguous terms).
4. **Marks optional sections** as "N/A" at `##` level if no wiki content maps
   to them. Remove `###`-level optional sub-sections that are not applicable.
5. **Removes template markers** — strip `(Mandatory)` and `(Optional)` markers
   from section headers.
6. **Sets Document Status to `Draft`** — the converted document always starts
   as a draft.

### Step 5 — Insert image placeholders

For every image attachment downloaded in Step 2, insert an **image placeholder
block** at the location in the document that corresponds to where it appeared
in the wiki page.

Use this exact format:

```markdown
> **[Image placeholder]**: `<image-filename>`
> *Context*: <brief description of what this image represents based on the
> surrounding wiki content — e.g., "Architecture diagram showing the HIF
> module interactions", "Screenshot of Simics boot log output">
>
> The image file is located in the adjacent `<images-directory>/` directory.
```

**Rules for image placeholders**:

- Place the placeholder at the most relevant location within the document
  based on where the image was referenced in the wiki page
- Use the exact downloaded filename (including extension)
- Write a meaningful context description derived from the surrounding wiki
  text (captions, nearby paragraphs, section title)
- If the wiki page embeds inline screenshots of terminal output, note that
  the content should ideally be converted to a code block in the final HLD;
  keep the placeholder for reference

### Step 6 — Convert diagrams to Mermaid (when possible)

The HLD guidelines require **Mermaid-only diagrams** (no embedded images).

- If a wiki diagram is simple enough to reconstruct (flowcharts, sequence
  diagrams, state machines), convert it to a Mermaid code block and replace
  the image placeholder.
- If the diagram is too complex to faithfully convert, keep the image
  placeholder and add a note:
  ```markdown
  > **TODO**: Convert this diagram to Mermaid syntax. Original image
  > retained as reference in `<images-directory>/<filename>`.
  ```

### Step 7 — Apply markdown style rules

Before writing the file, ensure compliance with `markdown-style.instructions.md`:

- One H1 per document
- ATX-style headings with space after `#`
- No skipped heading levels
- `-` for unordered lists, `1.` for ordered
- Backtick-fenced code blocks with language identifiers
- Descriptive link text (no bare URLs)
- Tables with header rows and aligned pipes
- Line length 80–120 characters for prose
- No trailing whitespace
- File ends with a single newline
- UTF-8 encoding, LF line endings

### Step 8 — Write the output files

1. Create the HLD file at the correct location:
   `docs/hld/<module_directory>/fw_hld_<feature_name>.md`
2. Confirm the images directory was created (or create it) alongside the HLD.
3. Report to the user:
   - Path to the generated HLD
   - Path to the images directory and number of images downloaded
   - List of remaining image placeholders that need resolution
   - List of sections that need human review (marked with `[placeholder]`
     or `TODO`)
   - Any wiki content that could not be mapped to the template
4. Proceed immediately to Step 9.

### Step 9 — Resolve image placeholders

Iterate over every remaining `[Image placeholder]` block in the generated HLD.
For each placeholder, present the image to the user (open it in the Simple
Browser if possible) along with the context description, then **propose** a
resolution strategy and **wait for the user to approve or choose** before
applying it.

**For each placeholder**:

1. Show the user the placeholder context and open/reference the downloaded
   image file.
2. Propose one of the three strategies below based on the image content:

   - **Convert to Mermaid** — if the image depicts a flowchart, sequence
     diagram, state machine, or other structured diagram that can be
     faithfully reproduced:
     - Replace the entire placeholder block with a ` ```mermaid ` code block
     - Verify the Mermaid syntax is valid

   - **Convert to text** — if the image shows terminal output, log snippets,
     configuration text, tables, or simple textual content:
     - Replace the placeholder with the appropriate markdown element (code
       block, table, or prose)
     - Use a fenced code block with the correct language identifier for
       terminal/log output

   - **Drop** — if the image is decorative, redundant, a screenshot of UI
     chrome, or cannot be meaningfully converted:
     - Remove the entire placeholder block
     - If the image carried any useful context, add a brief prose note in
       its place summarizing the information

3. **Ask the user to confirm** the proposed strategy before applying it.
   The user may choose a different strategy or provide additional guidance.
   Do not proceed with the resolution until the user explicitly approves.

4. Apply the approved strategy and briefly report the result.

5. Move to the next placeholder and repeat.

Once all placeholders are resolved, confirm to the user that no image
placeholders remain in the document.

### Step 10 — Clean up images directory

After all image placeholders have been resolved (Step 9), the downloaded
images are no longer needed in the repository.

1. **Ask the user** to confirm deletion of the images directory:
   ```
   All image placeholders have been resolved. The downloaded images in
   `<images-directory>/` are no longer needed.
   Do you want me to remove the images directory?
   ```
2. If the user confirms, delete the images directory:
   ```bash
   rm -rf docs/hld/<module_directory>/fw_hld_<feature_name>/
   ```
3. If the user declines, leave the directory in place and note that it
   should not be committed to the repository (images are not allowed in
   HLD documents per the guidelines).

## File Naming

**HLD file**: `fw_hld_<feature_name>.md`

- Use lowercase, underscores, no dates or version numbers

**Images directory**: `fw_hld_<feature_name>/`

- Same name as the HLD file without the `.md` extension
- Located in the same directory as the HLD file
- Contains all downloaded image attachments with their original filenames

**Location**: `docs/hld/<module_directory>/`

- `<module_directory>` corresponds to the firmware module the feature belongs
  to; infer from wiki content or ask the user

## Section Mapping

Use this table to map common wiki page patterns to HLD template sections:

| Wiki Content | HLD Section |
|-------------|-------------|
| Page title / introduction | 1.2 Purpose |
| Glossary / abbreviations | 1.1 Definitions, Acronyms, and Abbreviations |
| Requirements / scope | 1.3 FAS Coverage and Scope |
| Links / references | 1.4 References |
| Architecture / system overview | 2.1 System Context |
| Architecture diagrams | 2.2 Architecture Diagram |
| Affected components / modules list | 2.3 Affected Modules |
| Module-level design details | 3.x Detailed Design sections |
| Flow diagrams / sequence diagrams | 3.3 Flow Diagrams |
| Data structures / types | 3.4 Data Structures |
| API / interface definitions | 3.5 New/Modified Interfaces |
| State machines | 3.7 State Machine |
| Configuration / settings | 5. Configuration and Customization |
| Test plan / test cases | 6. Unit Testing Strategy |
| Appendix / extra material | 7. Appendices |

## Example Usage Prompts

- *"Convert this wiki page to an HLD: https://wiki.ith.intel.com/pages/viewpage.action?spaceKey=LADFW40G&title=My+Feature"*
- *"Draft an HLD from the 'NSC Boot Flow' Confluence page in the LADFW40G space"*
- *"Create an HLD document from wiki page ID 3769121182"*

## Important Notes

- The generated document is always a **Draft** — it requires human review
  before being submitted for formal approval
- Image placeholders are temporary — they exist only during the conversion
  process to preserve context while each image is resolved to Mermaid, text,
  or dropped. No placeholders should remain in the final document
- The images directory is a working artifact — once all placeholders are
  resolved, it must be removed (images are not allowed in HLD documents)
- If the wiki page is sparse, the skill should still produce the full HLD
  skeleton with populated sections where possible and `[placeholder]` markers
  elsewhere
- Always inform the user which sections need attention after generation

