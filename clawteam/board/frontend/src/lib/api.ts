const BASE = "/api"

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`)
  return res.json()
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`PATCH ${path} failed: ${res.status}`)
  return res.json()
}

export async function fetchOverview() {
  const res = await fetch(`${BASE}/overview`)
  if (!res.ok) throw new Error(`GET /overview failed: ${res.status}`)
  return res.json()
}

export async function createTask(
  team: string,
  data: { subject: string; owner?: string; description?: string },
) {
  return post(`/team/${encodeURIComponent(team)}/task`, data)
}

export async function updateTask(
  team: string,
  taskId: string,
  fields: Record<string, string>,
) {
  return patch(
    `/team/${encodeURIComponent(team)}/task/${encodeURIComponent(taskId)}`,
    fields,
  )
}

export async function addMember(
  team: string,
  data: { name: string; agentType: string },
) {
  return post(`/team/${encodeURIComponent(team)}/member`, data)
}

export async function sendMessage(
  team: string,
  data: { to: string; content: string; summary: string },
) {
  return post(`/team/${encodeURIComponent(team)}/message`, data)
}

export async function fetchProxy(url: string): Promise<string> {
  const res = await fetch(
    `${BASE}/proxy?url=${encodeURIComponent(url)}`,
  )
  if (!res.ok) throw new Error(`Proxy fetch failed: ${res.status}`)
  return res.text()
}
