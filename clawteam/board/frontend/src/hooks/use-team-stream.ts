import { useEffect, useRef, useState } from "react"
import type { TeamData } from "@/types"

interface TeamStreamState {
  data: TeamData | null
  isConnected: boolean
}

export function useTeamStream(teamName: string): TeamStreamState {
  const [data, setData] = useState<TeamData | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const lastPayload = useRef("")

  useEffect(() => {
    if (!teamName) {
      setData(null)
      setIsConnected(false)
      return
    }

    const es = new EventSource(
      `/api/events/${encodeURIComponent(teamName)}`,
    )

    es.onopen = () => setIsConnected(true)

    es.onmessage = (event) => {
      setIsConnected(true)
      if (event.data === lastPayload.current) return
      lastPayload.current = event.data
      try {
        const parsed: TeamData = JSON.parse(event.data)
        setData(parsed)
      } catch {
        console.error("Failed to parse SSE payload")
      }
    }

    es.onerror = () => setIsConnected(false)

    return () => {
      es.close()
      lastPayload.current = ""
    }
  }, [teamName])

  return { data, isConnected }
}
