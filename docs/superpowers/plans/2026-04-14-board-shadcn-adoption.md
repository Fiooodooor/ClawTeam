# Board shadcn Adoption Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the React board frontend to full shadcn/ui adoption — replace native `<select>` dropdowns, rebuild kanban with `Card`/`Badge`, and clean up modal form layouts with `FieldGroup`/`Field`.

**Architecture:** Work inside `clawteam/board/frontend/` (Vite + React + TS + Tailwind + shadcn/ui, style `base-nova`, base color `neutral`, icon library `lucide`). Install any missing shadcn primitives via `pnpm dlx shadcn@latest add <name>`. Every refactor preserves existing behavior — only visual/composition changes. Verify each task by running `pnpm build` and visually confirming in the running `clawteam board serve` dev instance at http://localhost:8081.

**Tech Stack:** React 18, TypeScript, Tailwind v3, shadcn/ui (radix base), lucide-react, @dnd-kit.

**Working directory for all commands:** `/home/jac/repos/ClawTeam/clawteam/board/frontend`

---

## File Inventory

**Existing shadcn primitives** (in `src/components/ui/`):
badge, button, card, dialog, input, label, scroll-area, select, sheet, textarea

**To install this plan:**
- `field` (FieldGroup/Field/FieldLabel/FieldDescription — used by all modals)

**Files modified:**
- `src/components/peek-panel.tsx` — 3 native `<select>` → shadcn `Select`
- `src/components/modals/inject-task.tsx` — native `<select>` → `Select`; form → `FieldGroup`
- `src/components/modals/add-agent.tsx` — native `<select>` → `Select`; form → `FieldGroup`
- `src/components/modals/set-context.tsx` — form → `FieldGroup`
- `src/components/modals/send-message.tsx` — form → `FieldGroup`
- `src/components/kanban/task-card.tsx` — div → `Card` + `Badge`
- `src/components/kanban/column.tsx` — count span → `Badge`

---

## Task 1: Replace native selects with shadcn Select in peek-panel

**Files:**
- Modify: `src/components/peek-panel.tsx` (3 native `<select>` at lines 100, 117, 134)

- [ ] **Step 1: Replace all three `<select>` blocks with shadcn `Select`**

Add imports at top:
```tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
```

Replace Status block:
```tsx
<Select value={task.status} onValueChange={(v) => save("status", v)}>
  <SelectTrigger className="w-full border-zinc-800 bg-zinc-900 text-zinc-200">
    <SelectValue />
  </SelectTrigger>
  <SelectContent className="border-zinc-800 bg-zinc-900">
    {STATUSES.map((s) => (
      <SelectItem key={s.value} value={s.value} className="text-zinc-200">
        {s.label}
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

Replace Priority block (same pattern, iterate `PRIORITIES`, value=`p`, label=capitalized).

Replace Assignee block (same pattern, iterate `members`; note: shadcn `Select` does NOT accept empty-string values — use sentinel `"__unassigned__"` and map in/out):
```tsx
<Select
  value={task.owner || "__unassigned__"}
  onValueChange={(v) => save("owner", v === "__unassigned__" ? "" : v)}
>
  <SelectTrigger className="w-full border-zinc-800 bg-zinc-900 text-zinc-200">
    <SelectValue />
  </SelectTrigger>
  <SelectContent className="border-zinc-800 bg-zinc-900">
    <SelectItem value="__unassigned__" className="text-zinc-200">Unassigned</SelectItem>
    {members.map((m) => (
      <SelectItem key={m.name} value={m.name} className="text-zinc-200">
        {m.name} ({m.agentType})
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

- [ ] **Step 2: Build and verify**

Run: `pnpm build`
Expected: build succeeds, no TS errors.

- [ ] **Step 3: Visual verify in browser**

Open peek panel on any task → confirm all 3 dropdowns render as styled shadcn popovers (not OS-native), changing value still calls `save()`, Assignee "Unassigned" round-trips to empty string.

- [ ] **Step 4: Commit**

```bash
git add src/components/peek-panel.tsx
git commit -m "refactor(board): replace native selects with shadcn Select in peek panel"
```

---

## Task 2: Replace native selects in modals

**Files:**
- Modify: `src/components/modals/inject-task.tsx` (native `<select>` at line 66)
- Modify: `src/components/modals/add-agent.tsx` (native `<select>` at line 70)

- [ ] **Step 1: inject-task.tsx — replace owner select**

Add imports:
```tsx
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
```

Replace the `<select>…</select>` block for `owner`:
```tsx
<Select
  value={owner || "__unassigned__"}
  onValueChange={(v) => setOwner(v === "__unassigned__" ? "" : v)}
>
  <SelectTrigger className="mt-1.5 w-full border-zinc-800 bg-zinc-900 text-zinc-200">
    <SelectValue />
  </SelectTrigger>
  <SelectContent className="border-zinc-800 bg-zinc-900">
    <SelectItem value="__unassigned__" className="text-zinc-200">Unassigned</SelectItem>
    {members.map((m) => (
      <SelectItem key={m.name} value={m.name} className="text-zinc-200">
        {m.name} ({m.agentType})
      </SelectItem>
    ))}
  </SelectContent>
</Select>
```

- [ ] **Step 2: add-agent.tsx — replace agentType select**

Add same Select imports. Replace `<select>` for `agentType`:
```tsx
<Select value={agentType} onValueChange={setAgentType}>
  <SelectTrigger className="mt-1.5 w-full border-zinc-800 bg-zinc-900 text-zinc-200">
    <SelectValue />
  </SelectTrigger>
  <SelectContent className="border-zinc-800 bg-zinc-900">
    {AGENT_TYPES.map((t) => (
      <SelectItem key={t} value={t} className="text-zinc-200">{t}</SelectItem>
    ))}
  </SelectContent>
</Select>
```

- [ ] **Step 3: Build and verify**

Run: `pnpm build`
Expected: build succeeds.

- [ ] **Step 4: Visual verify**

Open "Inject Task" and "Add Agent" dialogs → dropdowns are shadcn styled, selection persists.

- [ ] **Step 5: Commit**

```bash
git add src/components/modals/inject-task.tsx src/components/modals/add-agent.tsx
git commit -m "refactor(board): replace native selects with shadcn Select in modals"
```

---

## Task 3: Rebuild kanban task-card with Card + Badge

**Files:**
- Modify: `src/components/kanban/task-card.tsx` (currently 0 shadcn imports)
- Modify: `src/components/kanban/column.tsx` (count span → Badge)

- [ ] **Step 1: Read current task-card.tsx to capture exact props and behavior**

Run: Read `src/components/kanban/task-card.tsx` — note the props interface, dnd-kit `useSortable` wiring, avatar rendering, click-to-peek handler, and any priority/status coloring logic. Preserve all of that in Step 2.

- [ ] **Step 2: Refactor task-card.tsx to use Card + Badge**

Replace the outer draggable `<div>` with shadcn `Card` (keep the `ref={setNodeRef}`, `style`, `{...attributes}`, `{...listeners}`, `onClick` peek handler, and dnd drag transforms on the Card itself via `className`). Use `CardHeader` + `CardTitle` for the subject line, `CardContent` for the owner/avatar row.

Required structure (adapt prop/state names to whatever the file currently uses):
```tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"

<Card
  ref={setNodeRef}
  style={style}
  {...attributes}
  {...listeners}
  onClick={onPeek}
  className="cursor-grab border-zinc-800 bg-zinc-900/60 p-0 hover:border-zinc-700"
>
  <CardHeader className="p-3 pb-2">
    <CardTitle className="text-sm font-medium text-zinc-200">
      {task.subject}
    </CardTitle>
  </CardHeader>
  <CardContent className="flex items-center justify-between p-3 pt-0">
    <div className="flex items-center gap-2">
      {/* existing avatar circle — keep as-is */}
      <span className="text-xs text-zinc-400">{task.owner || "Unassigned"}</span>
    </div>
    {task.priority && task.priority !== "medium" && (
      <Badge variant="secondary" className="text-[10px]">
        {task.priority}
      </Badge>
    )}
  </CardContent>
</Card>
```

Preserve any existing priority→color mapping by conditionally choosing Badge `variant` (`destructive` for `urgent`/`high`, `secondary` for `low`, omit for `medium`).

- [ ] **Step 3: column.tsx — replace count pill with Badge**

Find the line that renders the task count next to the column title (likely `<span>…count…</span>`) and replace with:
```tsx
import { Badge } from "@/components/ui/badge"
…
<Badge variant="secondary">{tasks.length}</Badge>
```

- [ ] **Step 4: Build and verify**

Run: `pnpm build`
Expected: build succeeds.

- [ ] **Step 5: Visual verify**

- Cards render with shadcn `Card` styling (border + subtle bg).
- Drag-and-drop between columns still works (dnd-kit handlers intact).
- Click on card still opens peek panel.
- Column header shows shadcn `Badge` with task count.
- High/urgent priority cards show a destructive badge.

- [ ] **Step 6: Commit**

```bash
git add src/components/kanban/task-card.tsx src/components/kanban/column.tsx
git commit -m "refactor(board): adopt shadcn Card and Badge in kanban"
```

---

## Self-review notes

- Spec coverage: #1 dropdown unification → Tasks 1–2. #2 kanban Card/Badge → Task 3. #3 modal FieldGroup refactor intentionally deferred — the `field` primitive isn't installed yet and this plan scopes only the visible ugliness the user flagged. If desired, a follow-up plan should install `field` and migrate `inject-task`, `add-agent`, `set-context`, `send-message`, and `peek-panel` form layouts together.
- Empty-value workaround: shadcn `Select` (radix) disallows empty-string `SelectItem` values. Sentinel `"__unassigned__"` used everywhere owner/assignee can be cleared. Map in/out at the boundary.
- DnD preservation: Task 3 Step 2 explicitly keeps `setNodeRef`, `attributes`, `listeners`, and `style` on the Card — `Card` is just a styled div under the hood, so dnd-kit refs and drag handles work unchanged.
