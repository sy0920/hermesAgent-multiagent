import { create } from 'zustand'
import type { Expert, KanbanTask, Skill, Team } from './api/client'

export type TabKey = 'experts' | 'team' | 'kanban' | 'settings'

interface AppState {
  activeTab: TabKey
  experts: Expert[]
  skills: Skill[]
  teams: Team[]
  tasks: KanbanTask[]
  sseEnabled: boolean
  teamFinal: string | null

  setActiveTab: (tab: TabKey) => void
  setExperts: (experts: Expert[]) => void
  setSkills: (skills: Skill[]) => void
  setTeams: (teams: Team[]) => void
  setTasks: (tasks: KanbanTask[]) => void
  setSseEnabled: (v: boolean) => void
  setTeamFinal: (v: string | null) => void
}

export const useStore = create<AppState>((set) => ({
  activeTab: 'experts',
  experts: [],
  skills: [],
  teams: [],
  tasks: [],
  sseEnabled: false,
  teamFinal: null,

  setActiveTab: (tab) => set({ activeTab: tab }),
  setExperts: (experts) => set({ experts }),
  setSkills: (skills) => set({ skills }),
  setTeams: (teams) => set({ teams }),
  setTasks: (tasks) => set({ tasks }),
  setSseEnabled: (sseEnabled) => set({ sseEnabled }),
  setTeamFinal: (teamFinal) => set({ teamFinal }),
}))