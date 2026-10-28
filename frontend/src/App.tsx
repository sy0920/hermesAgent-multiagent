import { useEffect } from 'react'
import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { useStore } from './store'
import { fetchExperts, fetchTasks, fetchTeams, subscribeKanban } from './api/client'
import ExpertCenter from './pages/ExpertCenter'
import ExpertDetail from './pages/ExpertDetail'
import ExpertChat from './pages/ExpertChat'
import TeamCenter from './pages/TeamCenter'
import TeamDetail from './pages/TeamDetail'
import TeamChat from './pages/TeamChat'
import KanbanBoard from './pages/KanbanBoard'
import Settings from './pages/Settings'

const NAV_LINKS = [
  { to: '/experts', label: '专家中心', end: true },
  { to: '/teams', label: '专家团中心', end: false },
  { to: '/kanban', label: '看板', end: false },
  { to: '/settings', label: '配置', end: false },
]

export default function App() {
  const setExperts = useStore((s) => s.setExperts)
  const setTeams = useStore((s) => s.setTeams)
  const setTasks = useStore((s) => s.setTasks)
  const setSseEnabled = useStore((s) => s.setSseEnabled)

  useEffect(() => {
    fetchExperts().then(setExperts).catch(console.error)
    fetchTeams().then(setTeams).catch(console.error)
    fetchTasks().then(setTasks).catch(console.error)
  }, [setExperts, setTeams, setTasks])

  useEffect(() => {
    const stop = subscribeKanban(
      (tasks) => {
        setTasks(tasks)
        setSseEnabled(true)
      },
      () => setSseEnabled(false),
    )
    return stop
  }, [setTasks, setSseEnabled])

  return (
    <div>
      <header className="app-header">
        <span className="logo">🤖 Hermes 多 Agent 协作平台</span>
        <nav className="tabs">
          {NAV_LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) => `tab${isActive ? ' active' : ''}`}
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Navigate to="/experts" replace />} />
          <Route path="/experts" element={<ExpertCenter />} />
          <Route path="/experts/:id" element={<ExpertDetail />} />
          <Route path="/chat/expert/:id" element={<ExpertChat />} />
          <Route path="/teams" element={<TeamCenter />} />
          <Route path="/teams/:id" element={<TeamDetail />} />
          <Route path="/chat/team/:id" element={<TeamChat />} />
          <Route path="/kanban" element={<KanbanBoard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}