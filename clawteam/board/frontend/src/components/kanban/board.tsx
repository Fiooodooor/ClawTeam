import { DragDropProvider } from "@dnd-kit/react"
import { isSortable } from "@dnd-kit/react/sortable"
import { Column } from "./column"
import { updateTask } from "@/lib/api"
import type { TasksByStatus, TaskStatus } from "@/types"
import { TASK_STATUSES } from "@/types"

interface BoardProps {
  teamName: string
  tasks: TasksByStatus
  onPeek: (taskId: string) => void
}

export function Board({ teamName, tasks, onPeek }: BoardProps) {
  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-bold tracking-tight text-zinc-100">
          Mission Control
        </h2>
        <p className="text-sm text-zinc-500">
          Real-time distributed task execution
        </p>
      </div>
      <DragDropProvider
        onDragEnd={(event) => {
          if (event.canceled) return
          const { source } = event.operation
          if (!source || !isSortable(source)) return

          const taskId = String(source.id)
          const newStatus = String(source.group) as TaskStatus

          if (source.initialGroup !== source.group) {
            updateTask(teamName, taskId, { status: newStatus }).catch(
              console.error,
            )
          }
        }}
      >
        <div className="grid grid-cols-6 gap-4">
          {TASK_STATUSES.map((status) => (
            <Column
              key={status}
              status={status}
              tasks={tasks[status] || []}
              onPeek={onPeek}
            />
          ))}
        </div>
      </DragDropProvider>
    </div>
  )
}
