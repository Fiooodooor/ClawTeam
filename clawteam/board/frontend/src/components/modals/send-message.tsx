import { useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { sendMessage } from "@/lib/api"

interface SendMessageDialogProps {
  open: boolean
  onClose: () => void
  teamName: string
  targetInbox: string
  targetName: string
}

export function SendMessageDialog({
  open,
  onClose,
  teamName,
  targetInbox,
  targetName,
}: SendMessageDialogProps) {
  const [content, setContent] = useState("")
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit() {
    if (!content.trim()) return
    setSubmitting(true)
    try {
      await sendMessage(teamName, {
        to: targetInbox,
        content: content.trim(),
        summary: content.trim().substring(0, 50),
      })
      setContent("")
      onClose()
    } catch (e) {
      console.error("Failed to send message", e)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="border-zinc-800 bg-zinc-950 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">
            Send Message to {targetName}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="Type your message..."
            rows={4}
            className="border-zinc-800 bg-zinc-900 text-zinc-200"
            autoFocus
          />
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
              disabled={submitting || !content.trim()}
              className="bg-blue-600 text-white hover:bg-blue-700"
            >
              {submitting ? "Sending..." : "Send"}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
