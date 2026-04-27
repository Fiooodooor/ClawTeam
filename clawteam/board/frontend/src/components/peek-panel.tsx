import { useEffect, useMemo, useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { updateTask } from "@/lib/api"
import type { Task, Member, Message, TaskStatus } from "@/types"

interface PeekPanelProps {
  task: Task | null
  teamName: string
  members: Member[]
  messages: Message[]
  open: boolean
  onClose: () => void
}

const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: "pending", label: "Pending" },
  { value: "awaiting_approval", label: "Awaiting Approval" },
  { value: "in_progress", label: "In Progress" },
  { value: "completed", label: "Completed" },
  { value: "verified", label: "Verified" },
  { value: "blocked", label: "Blocked" },
]

const PRIORITIES = ["low", "medium", "high", "urgent"]

function formatTime(ts: string): string {
  return ts ? ts.slice(11, 19) : ""
}

export function PeekPanel({
  task,
  teamName,
  members,
  messages,
  open,
  onClose,
}: PeekPanelProps) {
  const [title, setTitle] = useState("")
  const [desc, setDesc] = useState("")

  useEffect(() => {
    if (task) {
      setTitle(task.subject)
      setDesc(task.description || "")
    }
  }, [task])

  const relatedMessages = useMemo(() => {
    if (!task) return []
    const shortId = task.id.substring(0, 8).toLowerCase()
    const fullId = task.id.toLowerCase()
    return messages
      .filter((m) => {
        const c = (m.content || "").toLowerCase()
        return c.includes(shortId) || c.includes(fullId)
      })
      .sort((a, b) => (b.timestamp || "").localeCompare(a.timestamp || ""))
  }, [task, messages])

  if (!task) return null

  function save(field: string, value: string) {
    updateTask(teamName, task!.id, { [field]: value }).catch(console.error)
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-[560px] overflow-y-auto border-l border-border bg-background sm:max-w-[560px]">
        <SheetHeader className="border-b border-border px-6 py-5">
          <SheetTitle className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground">
            #{task.id.substring(0, 8)}
          </SheetTitle>
        </SheetHeader>

        <div className="space-y-6 px-6 py-6">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Title
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => {
                if (title !== task.subject) save("subject", title)
              }}
              className="text-lg font-semibold"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Description
            </label>
            <Textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              onBlur={() => {
                if (desc !== (task.description || "")) save("description", desc)
              }}
              rows={5}
              placeholder="Add a description..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Status
              </label>
              <Select value={task.status} onValueChange={(v) => { if (v) save("status", v) }}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUSES.map((s) => (
                    <SelectItem key={s.value} value={s.value}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Priority
              </label>
              <Select
                value={task.priority || "medium"}
                onValueChange={(v) => { if (v) save("priority", v) }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p}>
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Assignee
              </label>
              <Select
                value={task.owner || "__unassigned__"}
                onValueChange={(v) => { if (v !== null) save("owner", v === "__unassigned__" ? "" : v) }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__unassigned__">Unassigned</SelectItem>
                  {members.map((m) => (
                    <SelectItem key={m.name} value={m.name}>
                      {m.name} ({m.agentType})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Created
              </label>
              <div className="px-1 py-2 text-sm text-muted-foreground">
                {task.createdAt
                  ? new Date(task.createdAt).toLocaleString()
                  : "-"}
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-5">
            <div className="mb-3 flex items-center justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Related Messages
              </label>
              <Badge variant="secondary" className="font-mono text-[10px]">
                {relatedMessages.length}
              </Badge>
            </div>
            {relatedMessages.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
                No messages reference this task yet.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {relatedMessages.map((msg, i) => (
                  <div
                    key={`${msg.timestamp}-${i}`}
                    className="rounded-md border border-border bg-muted/20 p-3"
                  >
                    <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="font-medium text-foreground">
                        {msg.fromLabel || msg.from || "SYS"}
                      </span>
                      <span className="text-muted-foreground">
                        {msg.isBroadcast ? "\u21A0" : "\u2192"}
                      </span>
                      <span className="font-medium text-foreground">
                        {msg.toLabel || msg.to || "ALL"}
                      </span>
                      <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                        {formatTime(msg.timestamp)}
                      </span>
                    </div>
                    <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-muted-foreground">
                      {msg.content}
                    </pre>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
