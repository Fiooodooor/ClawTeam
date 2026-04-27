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

interface TopbarProps {
  selectedTeam: string
  onTeamChange: (team: string) => void
  isConnected: boolean
}

export function Topbar({
  selectedTeam,
  onTeamChange,
  isConnected,
}: TopbarProps) {
  const [teams, setTeams] = useState<TeamOverview[]>([])

  useEffect(() => {
    fetchOverview().then(setTeams).catch(console.error)
  }, [])

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-6 border-b border-border bg-background/80 px-6 backdrop-blur">
      <div className="flex items-center gap-2.5">
        <div className="flex size-7 items-center justify-center rounded-md bg-foreground text-background">
          <svg
            width="14"
            height="14"
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
        <div className="flex items-baseline gap-2 leading-none">
          <span className="text-sm font-semibold tracking-tight text-foreground">
            ClawTeam
          </span>
          <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
            Nexus
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          Swarm
        </span>
        <Select
          value={selectedTeam}
          onValueChange={(v) => {
            if (v) onTeamChange(v)
          }}
        >
          <SelectTrigger className="h-8 w-[220px]">
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

      <div className="ml-auto flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5">
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
        <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Stream {isConnected ? "live" : "offline"}
        </span>
      </div>
    </header>
  )
}
