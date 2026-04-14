import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { createTask } from "@/lib/api"
import type { Member } from "@/types"

interface InjectTaskDialogProps {
  open: boolean
  onClose: () => void
  teamName: string
  members: Member[]
}

export function InjectTaskDialog({
  open,
  onClose,
  teamName,
  members,
}: InjectTaskDialogProps) {
  const [subject, setSubject] = useState("")
  const [owner, setOwner] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit() {
    if (!subject.trim()) return
    setSubmitting(true)
    try {
      await createTask(teamName, { subject, owner: owner || undefined })
      setSubject("")
      setOwner("")
      onClose()
    } catch (e) {
      console.error("Failed to create task", e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="border-zinc-800 bg-zinc-950 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Inject New Task</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-zinc-400">Description</Label>
            <Input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
              placeholder="Task description..."
              className="mt-1.5 border-zinc-800 bg-zinc-900 text-zinc-200"
              autoFocus
            />
          </div>
          <div>
            <Label className="text-zinc-400">Assign to</Label>
            <select
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              className="mt-1.5 w-full rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200"
            >
              <option value="">Unassigned</option>
              {members.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name} ({m.agentType})
                </option>
              ))}
            </select>
          </div>
          <div className="flex justify-end gap-3">
            <Button
              variant="outline"
              onClick={onClose}
              className="border-zinc-700 text-zinc-400"
            >
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitting || !subject.trim()}
              className="bg-blue-600 text-white hover:bg-blue-700"
            >
              {submitting ? "Deploying..." : "Deploy Task"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
