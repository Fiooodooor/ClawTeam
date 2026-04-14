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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { addMember } from "@/lib/api"

const AGENT_TYPES = [
  "general-purpose",
  "coder",
  "researcher",
  "reviewer",
  "tester",
]

interface AddAgentDialogProps {
  open: boolean
  onClose: () => void
  teamName: string
}

export function AddAgentDialog({
  open,
  onClose,
  teamName,
}: AddAgentDialogProps) {
  const [name, setName] = useState("")
  const [agentType, setAgentType] = useState("general-purpose")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit() {
    if (!name.trim()) return
    setSubmitting(true)
    try {
      await addMember(teamName, { name: name.trim(), agentType })
      setName("")
      setAgentType("general-purpose")
      onClose()
    } catch (e) {
      console.error("Failed to add agent", e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="border-zinc-800 bg-zinc-950 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Add Agent to Crew</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label className="text-zinc-400">Agent name</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. researcher"
              className="mt-1.5 border-zinc-800 bg-zinc-900 text-zinc-200"
              autoFocus
            />
          </div>
          <div>
            <Label className="text-zinc-400">Type</Label>
            <Select value={agentType} onValueChange={(v) => { if (v) setAgentType(v) }}>
              <SelectTrigger className="mt-1.5 w-full border-zinc-800 bg-zinc-900 text-zinc-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="border-zinc-800 bg-zinc-900">
                {AGENT_TYPES.map((t) => (
                  <SelectItem key={t} value={t} className="text-zinc-200">{t}</SelectItem>
                ))}
              </SelectContent>
            </Select>
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
              disabled={submitting || !name.trim()}
              className="bg-blue-600 text-white hover:bg-blue-700"
            >
              {submitting ? "Adding..." : "Add to Crew"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
