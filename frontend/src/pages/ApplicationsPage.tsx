import { useCallback, useEffect, useState } from 'react';
import { FileText, ShieldAlert, X } from 'lucide-react';
import { api } from '../api/client';
import type { AnalyticsSummary, ApplicationRecord } from '../api/types';

const STAGES = ['all', 'draft', 'applied', 'oa', 'screen', 'interview', 'offer', 'rejected'] as const;

export function ApplicationsPage() {
  const [apps, setApps] = useState<ApplicationRecord[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsSummary | null>(null);
  const [stageFilter, setStageFilter] = useState<string>('all');
  const [notesDraft, setNotesDraft] = useState<Record<number, string>>({});
  const [snapshotApp, setSnapshotApp] = useState<ApplicationRecord | null>(null);
  const [loading, setLoading] = useState(false);

  const loadApps = useCallback(async () => {
    setLoading(true);
    try {
      const [list, stats] = await Promise.all([
        api.listApplications(stageFilter),
        api.getAnalytics().catch(() => null),
      ]);
      setApps(Array.isArray(list) ? list : []);
      if (stats && Array.isArray(stats.track_skill_gaps)) {
        setAnalytics(stats);
      }
      const map: Record<number, string> = {};
      (Array.isArray(list) ? list : []).forEach((a) => {
        map[a.id] = a.recruiter_notes;
      });
      setNotesDraft(map);
    } finally {
      setLoading(false);
    }
  }, [stageFilter]);

  useEffect(() => {
    loadApps();
  }, [loadApps]);

  async function handleStageChange(appId: number, stage: string) {
    await api.updateApplication(appId, { stage });
    loadApps();
  }

  async function handleSaveNotes(appId: number) {
    await api.updateApplication(appId, { recruiter_notes: notesDraft[appId] ?? '' });
    loadApps();
  }

  async function handleSubmitDraft(appId: number) {
    await api.submitApplication(appId);
    loadApps();
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-white">Applications Mini-CRM</h1>
        <p className="text-sm text-slate-400">
          Track autofill drafts separately from submitted applications with immutable offline JD snapshots
        </p>
      </div>

      {analytics && (
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
            <div className="font-semibold text-white">Application Funnel</div>
            <div className="mt-1.5 flex flex-wrap gap-3 text-slate-300">
              <span>Submitted: <strong className="text-white">{analytics.total_submitted}</strong></span>
              <span>Drafts: <strong className="text-amber-300">{analytics.total_drafts}</strong></span>
              <span>Response Rate (OA/Interview+): <strong className="text-emerald-300">{analytics.response_rate_pct}%</strong></span>
            </div>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 text-xs">
            <div className="font-semibold text-white">Per-Track Tier A/B Missing Skills (Same Stack)</div>
            {analytics.track_skill_gaps.length === 0 ? (
              <div className="mt-1.5 text-slate-400">No Tier A/B gaps recorded yet.</div>
            ) : (
              <div className="mt-1.5 space-y-1">
                {analytics.track_skill_gaps.map((t) => (
                  <div key={t.resume_id} className="text-slate-300">
                    <strong className="text-sky-300">{t.track_name}</strong> ({t.evaluated_ab_jobs} A/B jobs):{' '}
                    {t.top_missing_skills.map((s) => `${s.skill} (${s.count})`).join(', ') || '0 gaps'}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stage Filter Tabs */}
      <div className="flex flex-wrap gap-2">
        {STAGES.map((st) => (
          <button
            key={st}
            onClick={() => setStageFilter(st)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium capitalize ${
              stageFilter === st
                ? 'bg-sky-600 text-white'
                : 'bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800'
            }`}
          >
            {st}
          </button>
        ))}
      </div>

      {loading && <p className="text-sm text-slate-400">Loading applications…</p>}

      {!loading && apps.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-8 text-center text-sm text-slate-400">
          No applications in stage “{stageFilter}”.
        </div>
      )}

      <div className="space-y-3">
        {apps.map((app) => (
          <div key={app.id} className="rounded-xl border border-slate-800 bg-slate-900/70 p-4 space-y-3">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-xs font-semibold uppercase text-sky-300">
                    {app.stage}
                  </span>
                  <h3 className="text-base font-semibold text-white">
                    {app.job_title ?? `Archived / Custom Role`} — {app.company_name ?? app.company_slug}
                  </h3>
                  {app.resume_filename_snapshot && (
                    <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-xs text-emerald-300">
                      Snapshot: {app.resume_filename_snapshot}
                    </span>
                  )}
                </div>
                <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                  <span>Portal: {app.portal_used || 'manual'}</span>
                  {app.autofill_started_at && (
                    <span>Autofill started: {new Date(app.autofill_started_at).toLocaleString()}</span>
                  )}
                  {app.submitted_at ? (
                    <span className="text-emerald-300">
                      Submitted: {new Date(app.submitted_at).toLocaleString()}
                    </span>
                  ) : (
                    <span className="text-amber-300">Draft — Not Submitted Yet</span>
                  )}
                  {app.cooldown && (
                    <span className="inline-flex items-center gap-1 text-slate-300">
                      <ShieldAlert className="h-3 w-3" />
                      30d Cooldown: {app.cooldown.apps_last_30d}/{app.cooldown.max_company_apps_30d}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {app.stage === 'draft' && (
                  <button
                    onClick={() => handleSubmitDraft(app.id)}
                    className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
                  >
                    Mark Submitted
                  </button>
                )}
                <select
                  aria-label={`Stage for application ${app.id}`}
                  value={app.stage}
                  onChange={(e) => handleStageChange(app.id, e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-white"
                >
                  {STAGES.filter((s) => s !== 'all').map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => setSnapshotApp(app)}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
                >
                  <FileText className="h-3.5 w-3.5" /> View Offline Snapshot
                </button>
              </div>
            </div>

            <div className="flex gap-2">
              <input
                type="text"
                value={notesDraft[app.id] ?? ''}
                onChange={(e) => setNotesDraft((prev) => ({ ...prev, [app.id]: e.target.value }))}
                placeholder="Recruiter notes / interview feedback…"
                className="flex-1 rounded-lg border border-slate-800 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
              />
              <button
                onClick={() => handleSaveNotes(app.id)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                Save Note
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Offline Snapshot Modal */}
      {snapshotApp && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          role="dialog"
          aria-label="Offline Snapshot Viewer"
        >
          <div className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 px-5 py-3">
              <h3 className="text-sm font-semibold text-white">
                Immutable Offline Snapshot — Application #{snapshotApp.id}
              </h3>
              <button
                onClick={() => setSnapshotApp(null)}
                className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto p-5 text-xs">
              <div>
                <span className="font-semibold text-slate-400">Frozen Resume File:</span>{' '}
                <span className="text-emerald-300">
                  {snapshotApp.resume_filename_snapshot || 'None recorded'}
                </span>
              </div>
              <div>
                <div className="mb-1 font-semibold text-slate-400">Submitted Answers JSON:</div>
                <pre className="rounded bg-slate-950 p-3 text-slate-200">
                  {JSON.stringify(snapshotApp.submitted_answers_json, null, 2)}
                </pre>
              </div>
              <div>
                <div className="mb-1 font-semibold text-slate-400">Offline JD Snapshot:</div>
                <pre className="whitespace-pre-wrap rounded bg-slate-950 p-3 text-slate-200">
                  {snapshotApp.jd_snapshot_text || 'No JD snapshot captured yet (still a draft).'}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

