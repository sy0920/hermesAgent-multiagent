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
  avatar: string
  description: string
  leader: string
  members: string[]
  created_at?: string
}

export interface TeamCreate {
  display_name: string
  description?: string
  leader: string
  members: string[]
}

export interface ChatResponse {
  reply: string
  session_id: string | null
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

export function createTeam(payload: TeamCreate): Promise<Team> {
  return request('/teams', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchTeam(teamId: string): Promise<Team> {
  return request(`/teams/${teamId}`)
}

export function expertChat(
  expertId: string,
  message: string,
  sessionId?: string | null,
): Promise<ChatResponse> {
  return request(`/experts/${encodeURIComponent(expertId)}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, session_id: sessionId ?? null }),
  })
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

// ---------------------------------------------------------------------------
// Scheduler sessions (central orchestrator / Plan confirm / resume)
// ---------------------------------------------------------------------------

export interface SubtaskView {
  subtask_id: string
  session_id: string
  round_no: number
  expert_id: string
  title: string
  instruction: string
  input_context: string
  deps: string[]
  status: string
  output: string
}

export interface SessionView {
  session_id: string
  group_id: string
  status: string
  user_query: string
  round_no: number
  plan_json: string
  final_report: string
  subtasks: SubtaskView[]
}

export function createSession(
  teamId: string,
  userQuery: string,
): Promise<{ session_id: string }> {
  return request(`/teams/${teamId}/sessions`, {
    method: 'POST',
    body: JSON.stringify({ user_query: userQuery }),
  })
}

export function fetchSession(sessionId: string): Promise<SessionView> {
  return request(`/sessions/${sessionId}`)
}

export function confirmPlan(
  sessionId: string,
  decision: 'confirm' | 'regenerate' | 'edit',
  feedback?: string,
): Promise<SessionView> {
  return request(`/sessions/${sessionId}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ decision, feedback: feedback ?? '' }),
  })
}

export function resumeSession(
  sessionId: string,
  feedback: string,
): Promise<SessionView> {
  return request(`/sessions/${sessionId}/resume`, {
    method: 'POST',
    body: JSON.stringify({ feedback }),
  })
}

// Shared helper to bridge session state changes to compute.
export function parsePlanJson(planJson: string): { summary: string; subtasks: SubtaskView[] } | null {
  if (!planJson) return null
  try {
    const obj = JSON.parse(planJson)
    if (obj && Array.isArray(obj.subtasks)) {
      return obj as { summary: string; subtasks: SubtaskView[] }
    }
    return null
  } catch {
    return null
  }
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