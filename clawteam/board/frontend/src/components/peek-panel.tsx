import { useEffect, useState } from "react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { updateTask } from "@/lib/api"
import type { Task, Member, TaskStatus } from "@/types"

interface PeekPanelProps {
  task: Task | null
  teamName: string
  members: Member[]
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

export function PeekPanel({
  task,
  teamName,
  members,
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

  if (!task) return null

  function save(field: string, value: string) {
    updateTask(teamName, task!.id, { [field]: value }).catch(console.error)
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent className="w-[520px] border-zinc-800 bg-[#09090b] sm:max-w-[520px]">
        <SheetHeader>
          <SheetTitle className="font-mono text-sm text-zinc-500">
            #{task.id.substring(0, 8)}
          </SheetTitle>
        </SheetHeader>

        <div className="mt-6 space-y-5">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
              Title
            </label>
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => {
                if (title !== task.subject) save("subject", title)
              }}
              className="border-zinc-800 bg-zinc-900 text-lg font-semibold text-zinc-100"
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
              Description
            </label>
            <Textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              onBlur={() => {
                if (desc !== (task.description || "")) save("description", desc)
              }}
              rows={5}
              className="border-zinc-800 bg-zinc-900 text-zinc-300"
              placeholder="Add a description..."
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                Status
              </label>
              <Select value={task.status} onValueChange={(v) => { if (v) save("status", v) }}>
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
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                Priority
              </label>
              <Select
                value={task.priority || "medium"}
                onValueChange={(v) => { if (v) save("priority", v) }}
              >
                <SelectTrigger className="w-full border-zinc-800 bg-zinc-900 text-zinc-200">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="border-zinc-800 bg-zinc-900">
                  {PRIORITIES.map((p) => (
                    <SelectItem key={p} value={p} className="text-zinc-200">
                      {p.charAt(0).toUpperCase() + p.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                Assignee
              </label>
              <Select
                value={task.owner || "__unassigned__"}
                onValueChange={(v) => { if (v !== null) save("owner", v === "__unassigned__" ? "" : v) }}
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
            </div>

            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-zinc-500">
                Created
              </label>
              <div className="px-1 py-2 text-sm text-zinc-400">
                {task.createdAt
                  ? new Date(task.createdAt).toLocaleString()
                  : "-"}
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
