import { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, Play, Plus, ShieldCheck } from 'lucide-react';
import { api } from '../api/client';
import type { CollectorHealthResponse, CollectorProgress, WatchedCompany } from '../api/types';

export function CollectorsPage() {
  const [health, setHealth] = useState<CollectorHealthResponse | null>(null);
  const [progress, setProgress] = useState<CollectorProgress | null>(null);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [schedulerHours, setSchedulerHours] = useState(4);
  const [watchlist, setWatchlist] = useState<WatchedCompany[]>([]);
  const [search, setSearch] = useState('');
  const [hoursOld, setHoursOld] = useState(24);
  const [slug, setSlug] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [atsType, setAtsType] = useState('greenhouse');
  const [tokenVal, setTokenVal] = useState('');
  const [banner, setBanner] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    const [h, p, w, sched] = await Promise.all([
      api.getCollectorHealth(),
      api.getCollectorProgress(),
      api.listWatchlist(),
      api.getSchedulerStatus(),
    ]);
    setHealth(h);
    setProgress(p);
    setWatchlist(w);
    setSchedulerRunning(sched.running);
    setSchedulerHours(sched.interval_hours);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!progress?.running) return;
    const timer = setInterval(() => {
      api.getCollectorProgress().then((p) => {
        setProgress(p);
        if (!p.running) loadAll();
      });
    }, 2000);
    return () => clearInterval(timer);
  }, [progress?.running, loadAll]);

  async function triggerRun(source: string) {
    try {
      await api.runCollectors(source, { background: true, hours_old: hoursOld });
      setBanner(`Started ${source} sweep in background.`);
      setProgress(await api.getCollectorProgress());
    } catch (err) {
      setBanner((err as Error).message);
    }
  }

  async function handleToggleScheduler() {
    try {
      const res = schedulerRunning ? await api.stopScheduler() : await api.startScheduler();
      setSchedulerRunning(res.running);
      setSchedulerHours(res.interval_hours);
      setBanner(
        res.running
          ? `Auto-scheduler started (runs every ${res.interval_hours}h).`
          : 'Auto-scheduler stopped.',
      );
    } catch (err) {
      setBanner((err as Error).message);
    }
  }

  async function handleVerify() {
    const res = await api.verifyWatchlist();
    setBanner(`Verified ${res.total_checked} boards: ${res.valid_count} OK, ${res.invalid_count} invalid (404).`);
    loadAll();
  }

  async function handleAddCompany(e: React.FormEvent) {
    e.preventDefault();
    const cleanSlug = slug.trim().toLowerCase();
    const config =
      atsType === 'greenhouse'
        ? { board_token: tokenVal.trim() || cleanSlug }
        : atsType === 'smartrecruiters'
          ? { company_id: tokenVal.trim() || cleanSlug }
          : { company_name: tokenVal.trim() || cleanSlug };
    await api.addCompany({
      slug: cleanSlug,
      display_name: displayName.trim(),
      employer_type: 'direct_product',
      ats_type: atsType,
      ats_config_json: config,
      is_watched: true,
    });
    setSlug('');
    setDisplayName('');
    setTokenVal('');
    loadAll();
  }

  const filteredWatchlist = watchlist.filter(
    (c) =>
      !search.trim() ||
      c.display_name.toLowerCase().includes(search.toLowerCase()) ||
      c.slug.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Collectors &amp; Watchlist</h1>
          <p className="text-sm text-slate-400">
            Direct ATS polling, JobSpy aggregators, circuit-breaker cooldown telemetry &amp; board health verifier
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="JobSpy Lookback Hours"
            value={hoursOld}
            onChange={(e) => setHoursOld(Number(e.target.value))}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-slate-200"
          >
            <option value={24}>JobSpy: 24h</option>
            <option value={168}>JobSpy: 7d (168h)</option>
            <option value={720}>JobSpy: 30d (720h)</option>
          </select>
          <button
            onClick={() => triggerRun('ats')}
            className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-3 py-2 text-xs font-medium text-white hover:bg-sky-500"
          >
            <Play className="h-3.5 w-3.5" /> Run ATS Sweep
          </button>
          <button
            onClick={() => triggerRun('jobspy')}
            className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-2 text-xs font-medium text-white hover:bg-slate-700"
          >
            <Play className="h-3.5 w-3.5" /> Run JobSpy
          </button>
          <button
            onClick={handleVerify}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-800"
          >
            <ShieldCheck className="h-3.5 w-3.5" /> Verify Boards
          </button>
          <button
            onClick={handleToggleScheduler}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium ${
              schedulerRunning
                ? 'bg-amber-600 text-white hover:bg-amber-500'
                : 'border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25'
            }`}
          >
            <Play className="h-3.5 w-3.5" />
            {schedulerRunning ? `Stop Auto-Scheduler (${schedulerHours}h)` : `Start Auto-Scheduler (${schedulerHours}h)`}
          </button>
        </div>
      </div>

      {banner && (
        <div className="rounded-lg border border-sky-500/40 bg-sky-500/10 p-3 text-xs text-sky-200">
          {banner}
        </div>
      )}

      {progress?.running && (
        <div className="rounded-xl border border-sky-500/40 bg-sky-500/10 p-4 text-xs text-sky-200">
          Running {progress.phase}: {progress.completed}/{progress.total || '?'} —{' '}
          {progress.current_item ?? 'initializing'} ({progress.new_so_far} new)
        </div>
      )}

      {health && (
        <div className="grid gap-3 md:grid-cols-4">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-xs text-slate-400">Total Sources</div>
            <div className="text-2xl font-bold text-white">{health.total_sources}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-xs text-emerald-400">Healthy</div>
            <div className="text-2xl font-bold text-emerald-300">{health.healthy_sources}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-xs text-amber-400">In Cooldown (429/403)</div>
            <div className="text-2xl font-bold text-amber-300">{health.cooldown_sources}</div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4">
            <div className="text-xs text-rose-400">Errors / 404 Config</div>
            <div className="text-2xl font-bold text-rose-300">{health.error_sources}</div>
          </div>
        </div>
      )}

      {/* Add Company */}
      <form onSubmit={handleAddCompany} className="grid gap-2 rounded-xl border border-slate-800 bg-slate-900/70 p-4 md:grid-cols-5">
        <input
          type="text"
          required
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          placeholder="slug (e.g. razorpay)"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
        />
        <input
          type="text"
          required
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Display Name"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
        />
        <select
          value={atsType}
          onChange={(e) => setAtsType(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
        >
          <option value="greenhouse">greenhouse</option>
          <option value="lever">lever</option>
          <option value="ashby">ashby</option>
          <option value="smartrecruiters">smartrecruiters</option>
        </select>
        <input
          type="text"
          value={tokenVal}
          onChange={(e) => setTokenVal(e.target.value)}
          placeholder="Board Token"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
        />
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500"
        >
          <Plus className="h-4 w-4" /> Add ATS Company
        </button>
      </form>

      {/* Watchlist Table */}
      <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter watched companies…"
          className="w-full max-w-sm rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white"
        />
        <div className="max-h-96 overflow-y-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 text-slate-400">
              <tr>
                <th className="py-2">Company</th>
                <th className="py-2">ATS</th>
                <th className="py-2">Health</th>
                <th className="py-2">Last Polled</th>
                <th className="py-2 text-right">Watched</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {filteredWatchlist.map((c) => (
                <tr key={c.slug}>
                  <td className="py-2 font-medium text-white">{c.display_name}</td>
                  <td className="py-2 text-slate-300">{c.ats_type}</td>
                  <td className="py-2">
                    <span
                      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 ${
                        c.health_status === 'ok'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : c.health_status === 'cooldown'
                            ? 'bg-amber-500/15 text-amber-300'
                            : 'bg-rose-500/15 text-rose-300'
                      }`}
                    >
                      <CheckCircle2 className="h-3 w-3" /> {c.health_status}
                    </span>
                  </td>
                  <td className="py-2 text-slate-400">
                    {c.last_polled_at ? new Date(c.last_polled_at).toLocaleString() : 'Never'}
                  </td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => api.toggleWatchCompany(c.slug, !c.is_watched).then(loadAll)}
                      className={`rounded px-2.5 py-0.5 text-xs ${
                        c.is_watched ? 'bg-sky-600/30 text-sky-300' : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {c.is_watched ? 'Watching' : 'Paused'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

