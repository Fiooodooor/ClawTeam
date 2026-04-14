import { Card } from "@/components/ui/card"
import type { TaskSummary } from "@/types"
import { STATUS_LABELS, STATUS_COLORS, TASK_STATUSES } from "@/types"

interface SummaryBarProps {
  summary: TaskSummary
}

export function SummaryBar({ summary }: SummaryBarProps) {
  return (
    <div className="grid grid-cols-6 gap-4">
      {TASK_STATUSES.map((status) => {
        const count = summary[status] ?? 0
        const color = STATUS_COLORS[status]
        return (
          <Card
            key={status}
            size="sm"
            className="relative flex flex-col gap-0 overflow-hidden bg-card/60 px-5 py-5 ring-0 backdrop-blur transition-colors hover:bg-card"
          >
            <span
              aria-hidden
              className="absolute inset-x-0 top-0 h-px"
              style={{
                background: `linear-gradient(90deg, transparent, ${color}, transparent)`,
              }}
            />
            <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
              {STATUS_LABELS[status]}
            </span>
            <span
              className="mt-3 text-4xl font-semibold leading-none tabular-nums"
              style={{ color: count > 0 ? color : "var(--muted-foreground)" }}
            >
              {count}
            </span>
          </Card>
        )
      })}
    </div>
  )
}
