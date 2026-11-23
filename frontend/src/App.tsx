import { useState } from 'react';
import {
  Activity,
  Briefcase,
  CheckSquare,
  FileText,
  KeyRound,
  ShieldCheck,
} from 'lucide-react';
import { getLocalToken, setLocalToken } from './api/client';
import { ApplicationsPage } from './pages/ApplicationsPage';
import { CollectorsPage } from './pages/CollectorsPage';
import { FactVaultPage } from './pages/FactVaultPage';
import { JobQueuePage } from './pages/JobQueuePage';
import { ResumesPage } from './pages/ResumesPage';

type NavKey = 'jobs' | 'applications' | 'vault' | 'resumes' | 'collectors';

const NAV_ITEMS: { key: NavKey; label: string; icon: typeof Briefcase }[] = [
  { key: 'jobs', label: 'Job Queue', icon: Briefcase },
  { key: 'applications', label: 'Applications CRM', icon: CheckSquare },
  { key: 'vault', label: 'Fact Vault & Backup', icon: ShieldCheck },
  { key: 'resumes', label: 'Resume Tracks', icon: FileText },
  { key: 'collectors', label: 'Collectors & Watchlist', icon: Activity },
];

export default function App() {
  const [page, setPage] = useState<NavKey>('jobs');
  const [tokenInput, setTokenInput] = useState('');
  const [hasToken, setHasToken] = useState<boolean>(() => Boolean(getLocalToken()));

  function handleSaveToken(e: React.FormEvent) {
    e.preventDefault();
    if (!tokenInput.trim()) return;
    setLocalToken(tokenInput);
    setHasToken(true);
    setTokenInput('');
  }

  return (
    <div className="flex min-h-screen bg-slate-950 text-slate-100">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-slate-800 bg-slate-900/90 p-4 flex flex-col justify-between">
        <div className="space-y-6">
          <div>
            <div className="text-lg font-bold tracking-tight text-white">JobAutomation</div>
            <div className="text-xs text-slate-400">Local India Tech Copilot • $0</div>
          </div>

          <nav className="space-y-1">
            {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setPage(key)}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  page === key
                    ? 'bg-sky-600 text-white'
                    : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                }`}
              >
                <Icon className="h-4 w-4" />
                <span>{label}</span>
              </button>
            ))}
          </nav>
        </div>

        <div className="rounded-lg border border-slate-800 bg-slate-950 p-3 text-xs text-slate-400">
          Loopback Auth:{' '}
          <span className={hasToken ? 'text-emerald-400' : 'text-amber-400'}>
            {hasToken ? 'Active Token' : 'Missing Token'}
          </span>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 p-6 overflow-y-auto">
        {!hasToken && (
          <form
            onSubmit={handleSaveToken}
            className="mb-5 flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-xs"
          >
            <KeyRound className="h-4 w-4 text-amber-300" />
            <span className="text-amber-200">
              Dev Mode: Paste token from <code>data/.local_token</code> to authenticate API requests:
            </span>
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="X-Local-Token"
              className="rounded border border-amber-500/40 bg-slate-950 px-2.5 py-1 text-white"
            />
            <button
              type="submit"
              className="rounded bg-amber-600 px-3 py-1 font-medium text-white hover:bg-amber-500"
            >
              Save Token
            </button>
          </form>
        )}

        {page === 'jobs' && <JobQueuePage />}
        {page === 'applications' && <ApplicationsPage />}
        {page === 'vault' && <FactVaultPage />}
        {page === 'resumes' && <ResumesPage />}
        {page === 'collectors' && <CollectorsPage />}
      </main>
    </div>
  );
}

