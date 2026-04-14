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
    <aside className="flex w-64 flex-col border-r border-border bg-background/80 px-6 py-8 backdrop-blur">
      <div className="mb-12 flex items-center gap-2.5">
        <div className="flex size-8 items-center justify-center rounded-md bg-foreground text-background">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-sm font-semibold tracking-tight text-foreground">
            ClawTeam
          </span>
          <span className="mt-0.5 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Nexus
          </span>
        </div>
      </div>

      <div className="mb-auto">
        <label className="mb-2 block text-[10px] font-medium uppercase tracking-[0.25em] text-muted-foreground">
          Active Swarm
        </label>
        <Select
          value={selectedTeam}
          onValueChange={(v) => {
            if (v) onTeamChange(v)
          }}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select team" />
          </SelectTrigger>
          <SelectContent>
            {teams.map((t) => (
              <SelectItem key={t.name} value={t.name}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2.5 rounded-md border border-border bg-card px-3 py-2.5">
        <span className={`relative flex size-2 ${isConnected ? "" : "opacity-60"}`}>
          {isConnected && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
          )}
          <span
            className={`relative inline-flex size-2 rounded-full ${
              isConnected ? "bg-emerald-400" : "bg-destructive"
            }`}
          />
        </span>
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          Stream {isConnected ? "live" : "offline"}
        </span>
      </div>
    </aside>
  )
}
