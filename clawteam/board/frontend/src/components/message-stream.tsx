import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { Message } from "@/types"

function formatTime(ts: string): string {
  return ts ? ts.slice(11, 19) : ""
}

function typeBadgeClass(msg: Message): string {
  if (msg.isBroadcast) return "bg-violet-500/15 text-violet-400 border-violet-500/20"
  if (msg.type && msg.type !== "message")
    return "bg-zinc-700/50 text-zinc-400 border-zinc-600/30"
  return "bg-blue-500/15 text-blue-400 border-blue-500/20"
}

interface MessageStreamProps {
  messages: Message[]
}

export function MessageStream({ messages }: MessageStreamProps) {
  const sorted = [...messages].sort((a, b) =>
    (b.timestamp || "").localeCompare(a.timestamp || ""),
  )

  return (
    <div className="flex flex-col rounded-lg border border-zinc-800 bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
        <span className="text-sm font-semibold text-zinc-200">
          Protocol Stream
        </span>
        <Badge variant="secondary" className="bg-zinc-800 text-zinc-400">
          {sorted.length} events
        </Badge>
      </div>
      <ScrollArea className="h-[420px]">
        <div className="flex flex-col gap-3 p-4">
          {sorted.length === 0 ? (
            <p className="py-10 text-center text-sm text-zinc-600">
              No activity recorded.
            </p>
          ) : (
            sorted.map((msg, i) => (
              <div
                key={`${msg.timestamp}-${i}`}
                className="rounded-md border border-zinc-800/50 bg-zinc-900/30 p-4"
              >
                <div className="mb-2 flex flex-wrap items-center gap-2 text-sm">
                  <Badge
                    variant="outline"
                    className={`text-[10px] font-bold uppercase ${typeBadgeClass(msg)}`}
                  >
                    {msg.type || "protocol"}
                  </Badge>
                  <span className="font-medium text-zinc-300">
                    {msg.fromLabel || msg.from || "SYS"}
                  </span>
                  <span className="text-zinc-600">
                    {msg.isBroadcast ? "\u21A0" : "\u2192"}
                  </span>
                  <span className="font-medium text-zinc-300">
                    {msg.toLabel || msg.to || "ALL"}
                  </span>
                  <span className="ml-auto font-mono text-xs text-zinc-600">
                    {formatTime(msg.timestamp)}
                  </span>
                </div>
                <pre className="whitespace-pre-wrap break-words rounded border border-zinc-800/30 bg-zinc-950/50 p-3 font-mono text-xs leading-relaxed text-zinc-400">
                  {msg.content}
                </pre>
              </div>
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  )
}
