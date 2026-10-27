import { useEffect } from 'react'
import { useStore, type TabKey } from './store'
import { fetchExperts, fetchTasks, fetchTeams, subscribeKanban } from './api/client'
import ExpertCenter from './pages/ExpertCenter'
import ExpertTeam from './pages/ExpertTeam'
import KanbanBoard from './pages/KanbanBoard'
import Settings from './pages/Settings'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'experts', label: '专家中心' },
  { key: 'team', label: '专家团' },
  { key: 'kanban', label: '看板' },
  { key: 'settings', label: '配置' },
]

export default function App() {
  const activeTab = useStore((s) => s.activeTab)
  const setActiveTab = useStore((s) => s.setActiveTab)
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
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab${activeTab === t.key ? ' active' : ''}`}
              onClick={() => setActiveTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="app-main">
        {activeTab === 'experts' && <ExpertCenter />}
        {activeTab === 'team' && <ExpertTeam />}
        {activeTab === 'kanban' && <KanbanBoard />}
        {activeTab === 'settings' && <Settings />}
      </main>
    </div>
  )
}