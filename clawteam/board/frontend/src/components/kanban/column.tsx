import { useDroppable } from "@dnd-kit/react"
import { TaskCard } from "./task-card"
import { Badge } from "@/components/ui/badge"
import type { Task, TaskStatus } from "@/types"
import { STATUS_LABELS, STATUS_COLORS } from "@/types"

interface ColumnProps {
  status: TaskStatus
  tasks: Task[]
  onPeek: (taskId: string) => void
}

export function Column({ status, tasks, onPeek }: ColumnProps) {
  const { ref } = useDroppable({ id: status, type: "column" })
  const color = STATUS_COLORS[status]

  return (
    <div className="flex min-h-[400px] flex-col rounded-lg border border-border bg-card/30 backdrop-blur">
      <div className="relative flex items-center justify-between px-4 py-3">
        <span
          aria-hidden
          className="absolute inset-x-0 top-0 h-px"
          style={{ background: `linear-gradient(90deg, transparent, ${color}, transparent)` }}
        />
        <span
          className="font-mono text-[10px] font-medium uppercase tracking-[0.2em]"
          style={{ color }}
        >
          {STATUS_LABELS[status]}
        </span>
        <Badge
          variant="secondary"
          className="h-5 min-w-5 justify-center px-1.5 font-mono text-[10px] tabular-nums"
        >
          {tasks.length}
        </Badge>
      </div>
      <div ref={ref} className="flex flex-1 flex-col gap-2.5 border-t border-border/60 p-3">
        {tasks.length === 0 ? (
          <p className="py-10 text-center font-mono text-[10px] uppercase tracking-[0.25em] text-muted-foreground/40">
            Empty
          </p>
        ) : (
          tasks.map((task, i) => (
            <TaskCard
              key={task.id}
              task={task}
              index={i}
              column={status}
              onPeek={onPeek}
            />
          ))
        )}
      </div>
    </div>
  )
}
