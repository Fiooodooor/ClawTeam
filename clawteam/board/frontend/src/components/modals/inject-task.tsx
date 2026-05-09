import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { createTask } from "@/lib/api"
import type { Member } from "@/types"

interface InjectTaskDialogProps {
  open: boolean
  onClose: () => void
  teamName: string
  members: Member[]
}

const PRIORITIES = ["low", "medium", "high", "urgent"]

export function InjectTaskDialog({
  open,
  onClose,
  teamName,
  members,
}: InjectTaskDialogProps) {
  const [subject, setSubject] = useState("")
  const [description, setDescription] = useState("")
  const [owner, setOwner] = useState("")
  const [priority, setPriority] = useState("medium")
  const [submitting, setSubmitting] = useState(false)

  function reset() {
    setSubject("")
    setDescription("")
    setOwner("")
    setPriority("medium")
  }

  async function handleSubmit() {
    if (!subject.trim()) return
    setSubmitting(true)
    try {
      await createTask(teamName, {
        subject,
        description: description || undefined,
        owner: owner || undefined,
        priority,
      })
      reset()
      onClose()
    } catch (e) {
      console.error("Failed to create task", e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Inject New Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-5">
          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Title
            </label>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit()
              }}
              placeholder="Short summary of the task..."
              autoFocus
            />
          </div>

          <div>
            <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
              Description
            </label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add context, acceptance criteria, or links..."
              rows={5}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
                Priority
              </label>
              <Select
                value={priority}
                onValueChange={(v) => { if (v) setPriority(v) }}
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
                value={owner || "__unassigned__"}
                onValueChange={(v) => { if (v !== null) setOwner(v === "__unassigned__" ? "" : v) }}
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
          </div>

          <div className="flex justify-end gap-3 border-t border-border pt-4">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting || !subject.trim()}
            >
              {submitting ? "Deploying..." : "Deploy Task"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
