import { useSortable } from "@dnd-kit/react/sortable"
import { AgentAvatar } from "@/components/agent-registry"
import type { Task, TaskStatus } from "@/types"
import { STATUS_COLORS } from "@/types"

interface TaskCardProps {
  task: Task
  index: number
  column: TaskStatus
  onPeek: (taskId: string) => void
}

export function TaskCard({ task, index, column, onPeek }: TaskCardProps) {
  const { ref } = useSortable({
    id: task.id,
    index,
    group: column,
    type: "task",
    accept: "task",
  })

  const color = STATUS_COLORS[column]

  return (
    <div
      ref={ref}
      onClick={() => onPeek(task.id)}
      className="cursor-pointer rounded border border-zinc-800 bg-zinc-900/60 p-3.5 transition-all hover:border-zinc-700 hover:bg-zinc-900"
      style={{
        boxShadow: "0 0 0 0px transparent",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.boxShadow = `0 0 12px -4px ${color}`
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = "0 0 0 0px transparent"
      }}
    >
      <div className="mb-1.5 font-mono text-[11px] text-zinc-600">
        #{task.id.substring(0, 8)}
      </div>
      <div className="text-sm font-medium leading-snug text-zinc-200">
        {task.subject}
      </div>
      {task.owner && (
        <div className="mt-2.5 flex items-center gap-2 text-xs text-zinc-400">
          <AgentAvatar name={task.owner} />
          {task.owner}
        </div>
      )}
      {column === "blocked" && task.blockedBy?.length > 0 && (
        <div className="mt-2 inline-block rounded bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-400">
          Blocked by: {task.blockedBy.join(", ")}
        </div>
      )}
    </div>
  )
}
