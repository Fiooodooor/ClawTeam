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
            className="flex flex-col items-center justify-center border-zinc-800 bg-zinc-950 px-4 py-6"
            style={{ borderTopColor: color, borderTopWidth: "2px" }}
          >
            <span
              className="text-4xl font-bold tabular-nums"
              style={{
                color,
                textShadow: count > 0 ? `0 0 20px ${color}` : "none",
              }}
            >
              {count}
            </span>
            <span className="mt-2 text-xs font-semibold uppercase tracking-widest text-zinc-500">
              {STATUS_LABELS[status]}
            </span>
          </Card>
        )
      })}
    </div>
  )
}
