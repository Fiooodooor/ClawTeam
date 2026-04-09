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
import { Label } from "@/components/ui/label"
import { createTask, fetchProxy } from "@/lib/api"
import type { Member } from "@/types"

interface SetContextDialogProps {
  open: boolean
  onClose: () => void
  teamName: string
  members: Member[]
}

export function SetContextDialog({
  open,
  onClose,
  teamName,
  members,
}: SetContextDialogProps) {
  const [url, setUrl] = useState("")
  const [text, setText] = useState("")
  const [owner, setOwner] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [statusMsg, setStatusMsg] = useState("")

  async function handleSubmit() {
    let description = text.trim()
    setSubmitting(true)
    try {
      if (url.trim()) {
        setStatusMsg("Fetching URL content...")
        const fetched = await fetchProxy(url.trim())
        description += "\n\n--- Extracted Context ---\n\n" + fetched
      }
      if (!description) {
        setSubmitting(false)
        setStatusMsg("")
        return
      }
      setStatusMsg("Injecting context...")
      await createTask(teamName, {
        subject: "Analyze Project Specification Context",
        description,
        owner: owner || undefined,
      })
      setUrl("")
      setText("")
      setOwner("")
      setStatusMsg("")
      onClose()
    } catch (e) {
      console.error("Failed to set context", e)
      setStatusMsg(`Error: ${e}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="border-zinc-800 bg-zinc-950 sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Set Mission Context</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-zinc-500">
          Feed a project specification or GitHub README to the lead agent.
        </p>
        <div className="space-y-4">
          <div>
            <Label className="text-zinc-400">Raw URL</Label>
            <Input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://raw.githubusercontent.com/..."
              className="mt-1.5 border-zinc-800 bg-zinc-900 text-zinc-200"
            />
          </div>
          <div>
            <Label className="text-zinc-400">Or direct text</Label>
            <Textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste project requirements..."
              rows={6}
              className="mt-1.5 border-zinc-800 bg-zinc-900 text-zinc-200"
            />
          </div>
          <div>
            <Label className="text-zinc-400">Assign to agent</Label>
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
          {statusMsg && (
            <p className="text-xs text-zinc-500">{statusMsg}</p>
          )}
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
              disabled={submitting}
              className="bg-emerald-600 text-white hover:bg-emerald-700"
            >
              {submitting ? "Processing..." : "Initialize Protocol"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
