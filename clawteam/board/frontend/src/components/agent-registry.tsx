import { Badge } from "@/components/ui/badge"
import type { Member } from "@/types"

function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++)
    hash = name.charCodeAt(i) + ((hash << 5) - hash)
  const colors = [
    "#f59e0b", "#3b82f6", "#10b981", "#ef4444", "#a855f7",
    "#ec4899", "#14b8a6", "#f97316", "#6366f1", "#84cc16",
  ]
  return colors[Math.abs(hash) % colors.length]!
}

export function AgentAvatar({ name }: { name: string }) {
  if (!name) return null
  return (
    <span
      className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
      style={{ backgroundColor: agentColor(name) }}
      title={name}
    >
      {name.slice(0, 2).toUpperCase()}
    </span>
  )
}

interface AgentRegistryProps {
  members: Member[]
  onMessageClick: (inboxName: string, displayName: string) => void
  onAddAgent: () => void
}

export function AgentRegistry({
  members,
  onMessageClick,
  onAddAgent,
}: AgentRegistryProps) {
  return (
    <div className="flex flex-col rounded-lg border border-zinc-800 bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-800 px-5 py-4">
        <span className="text-sm font-semibold text-zinc-200">
          Agent Registry
        </span>
        <Badge variant="secondary" className="bg-zinc-800 text-zinc-400">
          {members.length} active
        </Badge>
        <button
          onClick={onAddAgent}
          className="ml-auto rounded-md border border-zinc-700 bg-zinc-800/50 px-3 py-1 text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-200"
        >
          + Agent
        </button>
      </div>
      <div className="flex flex-col gap-2 overflow-y-auto p-4" style={{ maxHeight: 420 }}>
        {members.map((m) => (
          <button
            key={m.memberKey}
            onClick={() => onMessageClick(m.inboxName || m.name, m.name)}
            className="flex items-center gap-3 rounded-md border border-zinc-800/50 bg-zinc-900/50 px-4 py-3 text-left transition-colors hover:border-zinc-700 hover:bg-zinc-900"
          >
            <AgentAvatar name={m.name} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium text-zinc-200">
                {m.name}
              </div>
              <div className="text-xs text-blue-400">{m.agentType}</div>
            </div>
            <span
              className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                m.inboxCount > 0
                  ? "bg-red-500/15 text-red-400"
                  : "bg-zinc-800 text-zinc-500"
              }`}
            >
              {m.inboxCount} pending
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
