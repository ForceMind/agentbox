import { BackendStatus } from './components/BackendStatus'

export function App() {
  return (
    <main className="min-h-screen bg-slate-950 px-5 py-12 text-slate-100 sm:px-8">
      <section className="mx-auto flex min-h-[70vh] max-w-3xl flex-col justify-center">
        <p className="mb-4 font-mono text-xs uppercase tracking-[0.24em] text-cyan-300">
          AI Developer Infrastructure
        </p>
        <h1 className="text-5xl font-semibold tracking-tight sm:text-7xl">
          AgentBox
        </h1>
        <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
          Turn any Linux server into a remotely managed AI development
          workstation.
        </p>
        <div className="mt-10 rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-2xl shadow-cyan-950/20">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="font-medium text-slate-100">
                Engineering skeleton
              </h2>
              <p className="mt-1 text-sm text-slate-400">
                Product workflows are intentionally not implemented in Phase 2.
              </p>
            </div>
            <BackendStatus />
          </div>
        </div>
      </section>
    </main>
  )
}
