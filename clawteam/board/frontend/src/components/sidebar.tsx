import { useEffect, useState } from "react"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { fetchOverview } from "@/lib/api"
import type { TeamOverview } from "@/types"

interface SidebarProps {
  selectedTeam: string
  onTeamChange: (team: string) => void
  isConnected: boolean
}

export function Sidebar({
  selectedTeam,
  onTeamChange,
  isConnected,
}: SidebarProps) {
  const [teams, setTeams] = useState<TeamOverview[]>([])

  useEffect(() => {
    fetchOverview().then(setTeams).catch(console.error)
  }, [])

  return (
    <aside className="flex w-64 flex-col border-r border-zinc-800 bg-zinc-950 p-6">
      <div className="mb-10 flex items-center gap-3">
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-zinc-300"
        >
          <path d="M12 2L2 7l10 5 10-5-10-5z" />
          <path d="M2 17l10 5 10-5" />
          <path d="M2 12l10 5 10-5" />
        </svg>
        <span className="text-lg font-bold tracking-tight text-zinc-100">
          ClawTeam
        </span>
      </div>

      <div className="mb-auto">
        <label className="mb-2 block text-xs font-semibold uppercase tracking-widest text-zinc-500">
          Active Swarm
        </label>
        <Select value={selectedTeam} onValueChange={(v) => { if (v) onTeamChange(v) }}>
          <SelectTrigger className="w-full border-zinc-800 bg-zinc-900 text-zinc-200">
            <SelectValue placeholder="Select team" />
          </SelectTrigger>
          <SelectContent className="border-zinc-800 bg-zinc-900">
            {teams.map((t) => (
              <SelectItem key={t.name} value={t.name} className="text-zinc-200">
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
        <div
          className={`h-2.5 w-2.5 rounded-full ${
            isConnected
              ? "bg-emerald-500 shadow-[0_0_8px_theme(--color-status-completed)]"
              : "bg-red-500"
          }`}
        />
        <span className="text-sm text-zinc-400">
          {isConnected ? "Live" : "Disconnected"}
        </span>
      </div>
    </aside>
  )
}
