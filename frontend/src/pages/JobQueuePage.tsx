import { useCallback, useEffect, useState } from 'react';
import { EyeOff, RefreshCw, Search, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import type { JobCard, ResumeSummary } from '../api/types';
import { JobDetailDrawer } from '../components/JobDetailDrawer';

const TIERS = ['S', 'A', 'B', 'C'] as const;

const TIER_BADGE: Record<string, string> = {
  S: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  A: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  B: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  C: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
};

export function JobQueuePage() {
  const [jobs, setJobs] = useState<JobCard[]>([]);
  const [total, setTotal] = useState(0);
  const [resumes, setResumes] = useState<ResumeSummary[]>([]);
  const [selectedTiers, setSelectedTiers] = useState<string[]>([]);
  const [resumeId, setResumeId] = useState<string>('');
  const [fresh6h, setFresh6h] = useState(false);
  const [missingMax, setMissingMax] = useState<string>('');
  const [friction, setFriction] = useState<string>('');
  const [city, setCity] = useState('');
  const [ftsInput, setFtsInput] = useState('');
  const [ftsQuery, setFtsQuery] = useState('');
  const [onlyHidden, setOnlyHidden] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listJobs({
        tier: selectedTiers.length > 0 ? selectedTiers.join(',') : undefined,
        resume_id: resumeId ? Number(resumeId) : undefined,
        fresh_6h: fresh6h || undefined,
        missing_max: missingMax !== '' ? Number(missingMax) : undefined,
        friction: friction || undefined,
        city: city.trim() || undefined,
        fts_query: ftsQuery.trim() || undefined,
        only_hidden: onlyHidden || undefined,
      });
      setJobs(Array.isArray(data?.items) ? data.items : []);
      setTotal(data?.total ?? 0);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [selectedTiers, resumeId, fresh6h, missingMax, friction, city, ftsQuery, onlyHidden]);

  useEffect(() => {
    api
      .listResumes()
      .then((data) => setResumes(Array.isArray(data) ? data : []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  function toggleTier(t: string) {
    setSelectedTiers((prev) => (prev.includes(t) ? prev.filter((x) => x !== t) : [...prev, t]));
  }

  async function handleUnhide(jobId: number) {
    await api.updateJobStatus(jobId, { hidden_by_gate1: false, hidden_reason: null });
    loadJobs();
  }

  async function handleRescore() {
    setLoading(true);
    await api.rescoreJobs();
    await loadJobs();
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Job Queue</h1>
          <p className="text-sm text-slate-400">
            5-Gate filtered roles ranked by Option 1 Tier + Option 3 Semantic Bullet Alignment ({total} total)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setOnlyHidden(false)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              !onlyHidden ? 'bg-sky-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            Active Queue
          </button>
          <button
            onClick={() => setOnlyHidden(true)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium ${
              onlyHidden ? 'bg-amber-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'
            }`}
          >
            <EyeOff className="h-3.5 w-3.5" /> Hidden Audit (Gate 1)
          </button>
          <button
            onClick={handleRescore}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-800"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Re-score All
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/70 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-400">Tier:</span>
          {TIERS.map((t) => (
            <button
              key={t}
              onClick={() => toggleTier(t)}
              className={`rounded border px-2.5 py-1 text-xs font-semibold ${
                selectedTiers.includes(t)
                  ? TIER_BADGE[t]
                  : 'border-slate-700 bg-slate-950 text-slate-400 hover:text-white'
              }`}
            >
              Tier {t}
            </button>
          ))}

          <select
            aria-label="Resume Track Filter"
            value={resumeId}
            onChange={(e) => setResumeId(e.target.value)}
            className="ml-2 rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs text-slate-200"
          >
            <option value="">All Resume Tracks</option>
            {resumes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.track_name}
              </option>
            ))}
          </select>

          <select
            aria-label="Missing Skills Max"
            value={missingMax}
            onChange={(e) => setMissingMax(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs text-slate-200"
          >
            <option value="">Missing Skills: Any</option>
            <option value="0">0 Missing Primary</option>
            <option value="1">&le; 1 Missing Primary</option>
            <option value="2">&le; 2 Missing Primary</option>
            <option value="3">&le; 3 Missing Primary</option>
          </select>

          <select
            aria-label="Apply Friction"
            value={friction}
            onChange={(e) => setFriction(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs text-slate-200"
          >
            <option value="">All Friction</option>
            <option value="fast_apply">Fast Apply</option>
            <option value="enterprise_ats">Enterprise ATS</option>
          </select>

          <label className="ml-2 inline-flex cursor-pointer items-center gap-1.5 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={fresh6h}
              onChange={(e) => setFresh6h(e.target.checked)}
              className="rounded border-slate-700 bg-slate-950"
            />
            Fresh (&le; 6h)
          </label>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setFtsQuery(ftsInput);
          }}
          className="flex flex-wrap gap-2"
        >
          <div className="relative flex-1 min-w-[220px]">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              value={ftsInput}
              onChange={(e) => setFtsInput(e.target.value)}
              placeholder='FTS5 Boolean search (e.g. Python AND (Kafka OR Redis))'
              className="w-full rounded-lg border border-slate-700 bg-slate-950 py-1.5 pl-9 pr-3 text-sm text-white placeholder-slate-500"
            />
          </div>
          <input
            type="text"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="City (e.g. Bengaluru)"
            className="w-44 rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white placeholder-slate-500"
          />
          <button
            type="submit"
            className="rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-sky-500"
          >
            Search
          </button>
        </form>
      </div>

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3 text-sm text-rose-200">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-slate-400">Loading jobs…</p>}

      {!loading && jobs.length === 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-8 text-center text-sm text-slate-400">
          No jobs match the current filters.
        </div>
      )}

      {/* Job Cards */}
      <div className="space-y-3">
        {jobs.map((job) => (
          <div
            key={job.id}
            onClick={() => setSelectedJobId(job.id)}
            className="cursor-pointer rounded-xl border border-slate-800 bg-slate-900/70 p-4 transition hover:border-sky-500/50"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  {job.winning_score && (
                    <span
                      className={`rounded border px-2 py-0.5 text-xs font-semibold ${
                        TIER_BADGE[job.winning_score.tier] ?? 'border-slate-700 bg-slate-800'
                      }`}
                    >
                      Tier {job.winning_score.tier} • {job.winning_score.semantic_bullet_coverage_pct}%
                    </span>
                  )}
                  <h3 className="text-base font-semibold text-white">{job.title}</h3>
                  {job.req_id && (
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
                      {job.req_id}
                    </span>
                  )}
                  {job.parent_sibling_job_id && (
                    <span className="rounded bg-purple-500/20 px-2 py-0.5 text-xs text-purple-300">
                      Sibling Role
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-300">
                  {job.company_name} • {job.role_subtag || 'Engineering'} •{' '}
                  {job.normalized_city || 'India'}
                  {job.office_locality ? ` (${job.office_locality})` : ''} • {job.work_mode}
                  {job.salary_min_lpa || job.salary_max_lpa
                    ? ` • ₹${job.salary_min_lpa ?? '?'}–${job.salary_max_lpa ?? '?'} LPA`
                    : ''}
                </p>
                {job.winning_score && (
                  <div className="flex flex-wrap items-center gap-2 pt-1 text-xs">
                    <span className="inline-flex items-center gap-1 rounded bg-slate-800 px-2 py-0.5 text-sky-300">
                      <Sparkles className="h-3 w-3" /> Track: {job.winning_score.track_name}
                    </span>
                    {job.winning_score.missing_primary_skills_json.length > 0 && (
                      <span className="text-rose-300">
                        Missing: {job.winning_score.missing_primary_skills_json.join(', ')}
                      </span>
                    )}
                    {job.winning_score.cross_resume_alerts_count > 0 && (
                      <span className="rounded bg-amber-500/20 px-2 py-0.5 text-amber-300">
                        {job.winning_score.cross_resume_alerts_count} Cross-Resume Alert(s)
                      </span>
                    )}
                  </div>
                )}
                {job.hidden_by_gate1 && job.hidden_reason && (
                  <div className="mt-1 flex items-center gap-3 text-xs text-amber-300">
                    <span>Hidden Reason: {job.hidden_reason}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleUnhide(job.id);
                      }}
                      className="rounded bg-amber-600 px-2 py-0.5 text-white hover:bg-amber-500"
                    >
                      Unhide
                    </button>
                  </div>
                )}
              </div>
              <div className="text-right text-xs text-slate-400">
                <div>{job.apply_friction}</div>
                <div>{job.repost_count > 0 ? `${job.repost_count} mirror/repost(s)` : ''}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      <JobDetailDrawer
        jobId={selectedJobId}
        onClose={() => setSelectedJobId(null)}
        onJobUpdated={loadJobs}
      />
    </div>
  );
}

