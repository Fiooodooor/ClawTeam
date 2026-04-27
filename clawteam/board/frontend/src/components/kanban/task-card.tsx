import { useRef } from "react"
import { useSortable } from "@dnd-kit/react/sortable"
import { AgentAvatar } from "@/components/agent-registry"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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

  const downPos = useRef<{ x: number; y: number } | null>(null)
  const color = STATUS_COLORS[column]

  return (
    <Card
      ref={ref}
      onPointerDown={(e) => {
        downPos.current = { x: e.clientX, y: e.clientY }
      }}
      onClick={(e) => {
        const start = downPos.current
        downPos.current = null
        if (start) {
          const dx = e.clientX - start.x
          const dy = e.clientY - start.y
          if (dx * dx + dy * dy > 25) return
        }
        onPeek(task.id)
      }}
      size="sm"
      className="cursor-pointer gap-2 bg-card/60 py-3 ring-1 ring-border/60 transition-all hover:bg-card hover:ring-border hover:shadow-[0_0_14px_-4px_var(--task-glow)]"
      style={{ ["--task-glow" as never]: color }}
    >
      <CardHeader className="gap-1">
        <div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground/70">
          #{task.id.substring(0, 8)}
        </div>
        <CardTitle className="text-sm font-medium leading-snug text-foreground">
          {task.subject}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {task.owner && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <AgentAvatar name={task.owner} />
            {task.owner}
          </div>
        )}
        {column === "blocked" && task.blockedBy && task.blockedBy.length > 0 && (
          <Badge
            variant="destructive"
            className="self-start text-[11px]"
          >
            Blocked by: {task.blockedBy.join(", ")}
          </Badge>
        )}
      </CardContent>
    </Card>
  )
}
