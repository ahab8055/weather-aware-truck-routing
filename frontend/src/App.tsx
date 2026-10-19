import HealthStatus from './components/HealthStatus'
import Icon from './components/Icon'
import RoutePlanner from './features/routes/RoutePlanner'

function App() {
  return (
    <div className="flex min-h-dvh flex-col lg:h-dvh">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 bg-gradient-to-br from-navy-900 to-navy-800 px-4 py-3 lg:px-6">
        <div className="flex items-center gap-3">
          <span
            className="grid size-10 place-items-center rounded-xl bg-gradient-to-br from-brand-400 to-brand-600 text-ink shadow-lg shadow-brand-400/20"
            aria-hidden="true"
          >
            <Icon name="truck" size={22} />
          </span>
          <div>
            <h1 className="m-0 text-lg font-bold tracking-tight text-white lg:text-xl">
              Weather-Aware Truck Routing
            </h1>
            <p className="m-0 text-sm text-slate-400">
              Compare routes by weather risk, cargo weight and travel time.
            </p>
          </div>
        </div>
        <HealthStatus />
      </header>
      <main className="min-h-0 flex-1">
        <RoutePlanner />
      </main>
    </div>
  )
}

export default App
