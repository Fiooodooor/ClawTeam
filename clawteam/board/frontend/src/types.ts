export interface TeamOverview {
  name: string
  description: string
  leader: string
  members: number
  tasks: number
  pendingMessages: number
  membersOnline?: number
}

export interface TeamInfo {
  name: string
  leaderName: string
  description: string
  membersOnline?: number
}

export interface Member {
  name: string
  agentId: string
  agentType: string
  joinedAt: string
  memberKey: string
  inboxName: string
  inboxCount: number
  user?: string
  isRunning?: boolean
}

export interface Task {
  id: string
  subject: string
  description: string
  status: string
  priority: string
  owner: string
  createdAt: string
  blockedBy: string[]
}

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "awaiting_approval"
  | "completed"
  | "verified"
  | "blocked"

export const TASK_STATUSES: TaskStatus[] = [
  "pending",
  "awaiting_approval",
  "in_progress",
  "completed",
  "verified",
  "blocked",
]

export const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: "Pending",
  awaiting_approval: "Awaiting Approval",
  in_progress: "In Progress",
  completed: "Completed",
  verified: "Verified",
  blocked: "Blocked",
}

export const STATUS_COLORS: Record<TaskStatus, string> = {
  pending: "var(--color-status-pending)",
  awaiting_approval: "var(--color-status-approval)",
  in_progress: "var(--color-status-progress)",
  completed: "var(--color-status-completed)",
  verified: "var(--color-status-verified)",
  blocked: "var(--color-status-blocked)",
}

export interface TasksByStatus {
  pending: Task[]
  in_progress: Task[]
  awaiting_approval: Task[]
  completed: Task[]
  verified: Task[]
  blocked: Task[]
}

export interface TaskSummary {
  pending: number
  in_progress: number
  awaiting_approval: number
  completed: number
  verified: number
  blocked: number
  total: number
}

export interface Message {
  from: string
  to: string
  type: string
  fromKey?: string
  fromLabel?: string
  toKey?: string
  toLabel?: string
  isBroadcast: boolean
  content: string
  timestamp: string
  summary?: string
}

export interface TeamData {
  team: TeamInfo
  members: Member[]
  tasks: TasksByStatus
  taskSummary: TaskSummary
  messages: Message[]
}
