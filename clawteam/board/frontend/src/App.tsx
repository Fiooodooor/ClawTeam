import { createContext, useContext, useState } from "react"
import { Sidebar } from "@/components/sidebar"
import { SummaryBar } from "@/components/summary-bar"
import { AgentRegistry } from "@/components/agent-registry"
import { MessageStream } from "@/components/message-stream"
import { Board } from "@/components/kanban/board"
import { PeekPanel } from "@/components/peek-panel"
import { InjectTaskDialog } from "@/components/modals/inject-task"
import { SetContextDialog } from "@/components/modals/set-context"
import { AddAgentDialog } from "@/components/modals/add-agent"
import { SendMessageDialog } from "@/components/modals/send-message"
import { Button } from "@/components/ui/button"
import { useTeamStream } from "@/hooks/use-team-stream"
import type { TeamData } from "@/types"

interface TeamContextValue {
  teamName: string
  data: TeamData | null
  isConnected: boolean
}

const TeamContext = createContext<TeamContextValue>({
  teamName: "",
  data: null,
  isConnected: false,
})

export function useTeam() {
  return useContext(TeamContext)
}

export default function App() {
  const [teamName, setTeamName] = useState("")
  const { data, isConnected } = useTeamStream(teamName)

  const [peekTaskId, setPeekTaskId] = useState<string | null>(null)
  const [taskDialogOpen, setTaskDialogOpen] = useState(false)
  const [contextDialogOpen, setContextDialogOpen] = useState(false)
  const [addAgentOpen, setAddAgentOpen] = useState(false)
  const [messageTarget, setMessageTarget] = useState<{
    inbox: string
    name: string
  } | null>(null)

  const allTasks = data
    ? Object.values(data.tasks).flat()
    : []
  const peekTask = peekTaskId
    ? allTasks.find((t) => t.id === peekTaskId) ?? null
    : null

  return (
    <TeamContext.Provider value={{ teamName, data, isConnected }}>
      <div className="flex h-screen bg-[#09090b]">
        <Sidebar
          selectedTeam={teamName}
          onTeamChange={setTeamName}
          isConnected={isConnected}
        />
        <main className="flex-1 overflow-y-auto p-10">
          {!teamName ? (
            <div className="flex h-full flex-col items-center justify-center text-zinc-500">
              <p className="text-2xl font-semibold text-zinc-300">
                ClawTeam Nexus
              </p>
              <p className="mt-2 text-sm">
                Select a swarm to begin monitoring.
              </p>
            </div>
          ) : !data ? (
            <div className="flex h-full items-center justify-center text-zinc-500">
              Connecting...
            </div>
          ) : (
            <div className="space-y-8">
              <header className="flex items-start justify-between">
                <div>
                  <h1 className="text-3xl font-bold tracking-tight text-zinc-100">
                    {data.team.name}
                  </h1>
                  <p className="mt-1 text-sm text-zinc-500">
                    Led by {data.team.leaderName} &middot;{" "}
                    {data.members.length} members &middot;{" "}
                    {data.team.description}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setContextDialogOpen(true)}
                    className="border-emerald-800 bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20"
                  >
                    Set Context
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => setTaskDialogOpen(true)}
                    className="border-blue-800 bg-blue-500/10 text-blue-400 hover:bg-blue-500/20"
                  >
                    + New Task
                  </Button>
                </div>
              </header>
              <SummaryBar summary={data.taskSummary} />
              <div className="grid grid-cols-[2fr_1fr] gap-6">
                <MessageStream messages={data.messages} />
                <AgentRegistry
                  members={data.members}
                  onMessageClick={(inboxName, displayName) =>
                    setMessageTarget({ inbox: inboxName, name: displayName })
                  }
                  onAddAgent={() => setAddAgentOpen(true)}
                />
              </div>
              <Board
                teamName={teamName}
                tasks={data.tasks}
                onPeek={(taskId) => setPeekTaskId(taskId)}
              />
            </div>
          )}
        </main>
        <PeekPanel
          task={peekTask}
          teamName={teamName}
          members={data?.members ?? []}
          open={peekTaskId !== null}
          onClose={() => setPeekTaskId(null)}
        />
        <InjectTaskDialog
          open={taskDialogOpen}
          onClose={() => setTaskDialogOpen(false)}
          teamName={teamName}
          members={data?.members ?? []}
        />
        <SetContextDialog
          open={contextDialogOpen}
          onClose={() => setContextDialogOpen(false)}
          teamName={teamName}
          members={data?.members ?? []}
        />
        <AddAgentDialog
          open={addAgentOpen}
          onClose={() => setAddAgentOpen(false)}
          teamName={teamName}
        />
        <SendMessageDialog
          open={messageTarget !== null}
          onClose={() => setMessageTarget(null)}
          teamName={teamName}
          targetInbox={messageTarget?.inbox ?? ""}
          targetName={messageTarget?.name ?? ""}
        />
      </div>
    </TeamContext.Provider>
  )
}
