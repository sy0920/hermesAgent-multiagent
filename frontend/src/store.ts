import { create } from 'zustand'
import type { Expert, KanbanTask, Team } from './api/client'

export type TabKey = 'experts' | 'team' | 'kanban' | 'settings'

interface AppState {
  activeTab: TabKey
  experts: Expert[]
  teams: Team[]
  tasks: KanbanTask[]
  sseEnabled: boolean
  teamFinal: string | null

  setActiveTab: (tab: TabKey) => void
  setExperts: (experts: Expert[]) => void
  setTeams: (teams: Team[]) => void
  setTasks: (tasks: KanbanTask[]) => void
  setSseEnabled: (v: boolean) => void
  setTeamFinal: (v: string | null) => void
}

export const useStore = create<AppState>((set) => ({
  activeTab: 'experts',
  experts: [],
  teams: [],
  tasks: [],
  sseEnabled: false,
  teamFinal: null,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setExperts: (experts) => set({ experts }),
  setTeams: (teams) => set({ teams }),
  setTasks: (tasks) => set({ tasks }),
  setSseEnabled: (sseEnabled) => set({ sseEnabled }),
  setTeamFinal: (teamFinal) => set({ teamFinal }),
}))

// Map a profile id ("sql", "expert-1719...") to its display name.
export function expertNameById(id: string | null | undefined): string {
  if (!id) return '未分配'
  const expert = useStore.getState().experts.find((e) => e.id === id)
  return expert ? expert.display_name : id
}