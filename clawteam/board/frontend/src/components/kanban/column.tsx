import { useDroppable } from "@dnd-kit/react"
import { TaskCard } from "./task-card"
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
    <div className="flex min-h-[400px] flex-col rounded-lg border border-zinc-800 bg-zinc-950/60">
      <div
        className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900/30 px-4 py-3"
        style={{ borderTopColor: color, borderTopWidth: "2px" }}
      >
        <span
          className="text-xs font-bold uppercase tracking-wider"
          style={{ color }}
        >
          {STATUS_LABELS[status]}
        </span>
        <span className="font-mono text-xs text-zinc-500">{tasks.length}</span>
      </div>
      <div ref={ref} className="flex flex-1 flex-col gap-2.5 p-3">
        {tasks.length === 0 ? (
          <p className="py-8 text-center font-mono text-[11px] uppercase tracking-widest text-zinc-700">
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
