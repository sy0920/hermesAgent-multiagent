// Typed API client for the Hermes multi-agent platform backend.

export interface Expert {
  id: string
  display_name: string
  avatar: string
  persona: string
  expertise: string
  prompt: string
  model: string
  skills: string[]
  status: string
}

export interface ExpertCreate {
  display_name: string
  persona: string
  expertise: string
  prompt: string
  model?: string
  skills?: string[]
  avatar?: string
}

export interface Skill {
  name: string
  description: string
}

export interface KanbanTask {
  id: string
  title: string
  status: 'todo' | 'ready' | 'doing' | 'done' | 'blocked' | string
  assignee: string | null
  parents: string[]
  children: string[]
}

export interface KanbanTaskDetail extends KanbanTask {
  body: string
  summary: string | null
  metadata: Record<string, unknown>
  runs: unknown[]
}

export interface Team {
  id: string
  display_name: string
  members: string[]
}

export interface TeamFinal {
  report: string | null
}

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* ignore parse errors */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  return res.json() as Promise<T>
}

export function fetchExperts(): Promise<Expert[]> {
  return request('/experts')
}

export function createExpert(payload: ExpertCreate): Promise<Expert> {
  return request('/experts', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchSkills(): Promise<Skill[]> {
  return request('/skills')
}

export function deleteExpert(name: string): Promise<{ ok: boolean }> {
  return request(`/experts/${encodeURIComponent(name)}`, { method: 'DELETE' })
}

export function fetchTasks(): Promise<KanbanTask[]> {
  return request('/kanban/tasks')
}

export function fetchTask(id: string): Promise<KanbanTaskDetail> {
  return request(`/kanban/tasks/${id}`)
}

export function runTask(id: string): Promise<{ run_id: string; status: string }> {
  return request(`/tasks/${id}/run`, { method: 'POST' })
}

export function unblockTask(id: string): Promise<{ ok: boolean }> {
  return request(`/kanban/tasks/${id}/unblock`, { method: 'POST' })
}

export function fetchTeams(): Promise<Team[]> {
  return request('/teams')
}

export function invokeTeam(
  teamId: string,
  requestBody: string,
): Promise<{ orchestrator_task_id: string }> {
  return request(`/teams/${teamId}/invoke`, {
    method: 'POST',
    body: JSON.stringify({ request: requestBody }),
  })
}

export function fetchTeamFinal(teamId: string): Promise<TeamFinal> {
  return request(`/teams/${teamId}/final`)
}

// SSE subscription with auto-reconnect. Returns an unsubscribe function.
export function subscribeKanban(
  onUpdate: (tasks: KanbanTask[]) => void,
  onDisconnect?: () => void,
): () => void {
  const src = new EventSource(`${BASE}/kanban/events`)
  src.addEventListener('update', (ev) => {
    try {
      const payload = JSON.parse((ev as MessageEvent).data) as {
        type: 'update'
        tasks: KanbanTask[]
      }
      onUpdate(payload.tasks)
    } catch {
      /* ignore malformed frames */
    }
  })
  if (onDisconnect) {
    src.onerror = () => onDisconnect()
  }
  return () => src.close()
}

export async function fetchHealth(): Promise<{ status: string }> {
  return request('/health')
}