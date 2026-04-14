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
      <div className="flex h-screen bg-background text-foreground">
        <Sidebar
          selectedTeam={teamName}
          onTeamChange={setTeamName}
          isConnected={isConnected}
        />
        <main className="atmosphere dot-grid relative flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1600px] px-10 py-12">
          {!teamName ? (
            <div className="flex h-[80vh] flex-col items-center justify-center text-center">
              <div className="text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground">
                ClawTeam
              </div>
              <h1 className="mt-4 text-5xl font-semibold tracking-tight text-foreground">
                Mission Control
              </h1>
              <p className="mt-3 max-w-md text-sm text-muted-foreground">
                Select an active swarm from the sidebar to begin observing agent
                coordination in real time.
              </p>
            </div>
          ) : !data ? (
            <div className="flex h-[80vh] items-center justify-center text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-2">
                <span className="size-1.5 animate-pulse rounded-full bg-foreground/60" />
                Connecting to {teamName}…
              </span>
            </div>
          ) : (
            <div className="flex flex-col gap-10">
              <header className="flex items-end justify-between gap-6 border-b border-border pb-8">
                <div>
                  <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.3em] text-muted-foreground">
                    <span>Swarm</span>
                    <span className="size-1 rounded-full bg-muted-foreground/60" />
                    <span className="font-mono normal-case tracking-normal">
                      {data.members.length} agents
                    </span>
                  </div>
                  <h1 className="mt-3 text-4xl font-semibold leading-none tracking-tight text-foreground">
                    {data.team.name}
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm text-muted-foreground">
                    Led by{" "}
                    <span className="text-foreground">{data.team.leaderName}</span>
                    {data.team.description ? ` · ${data.team.description}` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    onClick={() => setContextDialogOpen(true)}
                  >
                    Set Context
                  </Button>
                  <Button onClick={() => setTaskDialogOpen(true)}>
                    New Task
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
          </div>
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
