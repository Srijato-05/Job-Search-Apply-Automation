import { useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  GitCompare,
  Play,
  ShieldAlert,
  X,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import type { CooldownStatus, JobDetail, JobDiffResponse } from '../api/types';

interface Props {
  jobId: number | null;
  onClose: () => void;
  onJobUpdated?: () => void;
}

const TIER_STYLES: Record<string, string> = {
  S: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
  A: 'bg-sky-500/20 text-sky-300 border-sky-500/40',
  B: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  C: 'bg-rose-500/20 text-rose-300 border-rose-500/40',
};

export function JobDetailDrawer({ jobId, onClose, onJobUpdated }: Props) {
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [cooldown, setCooldown] = useState<CooldownStatus | null>(null);
  const [diff, setDiff] = useState<JobDiffResponse | null>(null);
  const [selectedSiblingId, setSelectedSiblingId] = useState<number | null>(null);
  const [selectedResumeIdx, setSelectedResumeIdx] = useState(0);
  const [activeTab, setActiveTab] = useState<'proof' | 'diff' | 'jd'>('proof');
  const [showRawJd, setShowRawJd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [draftId, setDraftId] = useState<number | null>(null);

  useEffect(() => {
    if (jobId === null) {
      setDetail(null);
      setCooldown(null);
      setDiff(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setActionMsg(null);
    setDraftId(null);
    setActiveTab('proof');
    setSelectedResumeIdx(0);

    api
      .getJobDetail(jobId)
      .then(async (data) => {
        if (cancelled) return;
        setDetail(data);
        if (data.company_slug) {
          try {
            const cd = await api.getCooldown(data.company_slug);
            if (!cancelled) setCooldown(cd);
          } catch {
            // ignore cooldown fetch failure
          }
        }
        if (data.sibling_jobs.length > 0) {
          const sibId = data.sibling_jobs[0].id;
          setSelectedSiblingId(sibId);
          try {
            const d = await api.getJobDiff(data.id, sibId);
            if (!cancelled) setDiff(d);
          } catch {
            // ignore diff fetch error
          }
        } else {
          setSelectedSiblingId(null);
          setDiff(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [jobId]);

  if (jobId === null) return null;

  const activeScore = detail?.all_scores[selectedResumeIdx] ?? detail?.all_scores[0] ?? null;

  async function handleSelectSibling(sibId: number) {
    if (!detail) return;
    setSelectedSiblingId(sibId);
    const d = await api.getJobDiff(detail.id, sibId);
    setDiff(d);
  }

  async function handleStartDraft() {
    if (!detail) return;
    try {
      const app = await api.startDraft({
        job_id: detail.id,
        company_slug: detail.company_slug,
        resume_id: detail.winning_score?.resume_id,
        portal_used: detail.sources[0]?.portal_name ?? 'manual',
        detection_method: 'dashboard',
      });
      setDraftId(app.id);
      setActionMsg(`Draft #${app.id} created (status: draft).`);
    } catch (err) {
      setActionMsg((err as Error).message);
    }
  }

  async function handleMarkApplied() {
    if (!detail) return;
    try {
      let targetAppId = draftId;
      if (targetAppId === null) {
        const draft = await api.startDraft({
          job_id: detail.id,
          company_slug: detail.company_slug,
          resume_id: detail.winning_score?.resume_id,
          portal_used: detail.sources[0]?.portal_name ?? 'manual',
          detection_method: 'dashboard',
        });
        targetAppId = draft.id;
      }
      const sub = await api.submitApplication(targetAppId, {
        resume_id: detail.winning_score?.resume_id,
      });
      setDraftId(sub.id);
      setActionMsg(`Submitted! Immutable snapshot saved (Application #${sub.id}).`);
      onJobUpdated?.();
    } catch (err) {
      setActionMsg((err as Error).message);
    }
  }

  async function handleToggleHidden() {
    if (!detail) return;
    const updated = await api.updateJobStatus(detail.id, {
      hidden_by_gate1: !detail.hidden_by_gate1,
      hidden_reason: detail.hidden_by_gate1 ? null : 'Manually hidden from queue',
    });
    setDetail((prev) =>
      prev ? { ...prev, hidden_by_gate1: updated.hidden_by_gate1, hidden_reason: updated.hidden_reason } : null,
    );
    onJobUpdated?.();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs"
      role="dialog"
      aria-label="Job Detail Drawer"
    >
      <div className="flex h-full w-full max-w-4xl flex-col border-l border-slate-800 bg-slate-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-slate-800 px-6 py-4">
          <div className="space-y-1">
            {detail ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  {detail.winning_score && (
                    <span
                      className={`rounded border px-2 py-0.5 text-xs font-semibold ${
                        TIER_STYLES[detail.winning_score.tier] ?? 'border-slate-700 bg-slate-800'
                      }`}
                    >
                      Tier {detail.winning_score.tier} ({detail.winning_score.semantic_bullet_coverage_pct}%)
                    </span>
                  )}
                  <h2 className="text-lg font-semibold text-white">{detail.title}</h2>
                  {detail.req_id && (
                    <span className="rounded bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-300">
                      {detail.req_id}
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-300">
                  {detail.company_name} • {detail.role_subtag || 'Engineering'} •{' '}
                  {detail.normalized_city || 'India'} ({detail.work_mode})
                </p>
                {cooldown && (
                  <div
                    className={`mt-1 inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs ${
                      cooldown.is_at_limit
                        ? 'bg-rose-500/20 text-rose-300'
                        : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    <ShieldAlert className="h-3.5 w-3.5" />
                    <span>
                      30d Cooldown: {cooldown.apps_last_30d}/{cooldown.max_company_apps_30d} submitted
                      {cooldown.warning_message ? ` — ${cooldown.warning_message}` : ''}
                    </span>
                  </div>
                )}
              </>
            ) : (
              <p className="text-sm text-slate-400">Loading job details…</p>
            )}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white"
            aria-label="Close drawer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Actions & Portal links */}
        {detail && (
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 bg-slate-950/60 px-6 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={handleStartDraft}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-100 hover:bg-slate-700"
              >
                <Play className="h-3.5 w-3.5" /> Start Draft
              </button>
              <button
                onClick={handleMarkApplied}
                className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500"
              >
                <CheckCircle2 className="h-3.5 w-3.5" /> Mark Applied (Freeze Snapshot)
              </button>
              <button
                onClick={handleToggleHidden}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                {detail.hidden_by_gate1 ? 'Unhide to Queue' : 'Hide (Gate 1)'}
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {detail.sources.map((src) => (
                <a
                  key={src.id}
                  href={src.apply_url || src.job_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded border border-slate-700 px-2.5 py-1 text-xs text-sky-300 hover:bg-slate-800"
                >
                  {src.portal_name} <ExternalLink className="h-3 w-3" />
                </a>
              ))}
            </div>
          </div>
        )}

        {actionMsg && (
          <div className="border-b border-emerald-500/30 bg-emerald-500/10 px-6 py-2 text-xs text-emerald-200">
            {actionMsg}
          </div>
        )}

        {/* Tabs */}
        <div className="flex border-b border-slate-800 px-6 text-sm">
          <button
            onClick={() => setActiveTab('proof')}
            className={`border-b-2 px-4 py-2.5 font-medium ${
              activeTab === 'proof'
                ? 'border-sky-400 text-sky-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Option 1+3 Bullet Proof
          </button>
          <button
            onClick={() => setActiveTab('diff')}
            className={`inline-flex items-center gap-1.5 border-b-2 px-4 py-2.5 font-medium ${
              activeTab === 'diff'
                ? 'border-sky-400 text-sky-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <GitCompare className="h-4 w-4" />
            Sibling JD Diff ({detail?.sibling_jobs.length ?? 0})
          </button>
          <button
            onClick={() => setActiveTab('jd')}
            className={`border-b-2 px-4 py-2.5 font-medium ${
              activeTab === 'jd'
                ? 'border-sky-400 text-sky-300'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            Full / Cleaned JD
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading && <p className="text-sm text-slate-400">Loading analysis…</p>}

          {!loading && detail && activeTab === 'proof' && (
            <div className="space-y-5">
              {detail.all_scores.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {detail.all_scores.map((sc, idx) => (
                    <button
                      key={sc.resume_id}
                      onClick={() => setSelectedResumeIdx(idx)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-medium ${
                        idx === selectedResumeIdx
                          ? 'border-sky-500 bg-sky-500/20 text-sky-200'
                          : 'border-slate-800 bg-slate-950 text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      {sc.track_name} — Tier {sc.tier} ({sc.semantic_bullet_coverage_pct}%)
                      {sc.is_winning_resume ? ' ★ Winner' : ''}
                    </button>
                  ))}
                </div>
              )}

              {activeScore && (
                <>
                  {/* Option 1 Skills Matrix */}
                  <div className="grid gap-3 rounded-lg border border-slate-800 bg-slate-950/60 p-4 md:grid-cols-3">
                    <div>
                      <div className="mb-1 text-xs font-semibold text-emerald-400">
                        Matched Primary ({activeScore.matched_primary_skills_json.length})
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {activeScore.matched_primary_skills_json.map((s) => (
                          <span key={s} className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-xs text-emerald-300">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs font-semibold text-rose-400">
                        Missing Primary ({activeScore.missing_primary_skills_json.length})
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {activeScore.missing_primary_skills_json.map((s) => (
                          <span key={s} className="rounded bg-rose-500/15 px-1.5 py-0.5 text-xs text-rose-300">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-1 text-xs font-semibold text-amber-400">
                        Missing Bonus ({activeScore.missing_secondary_skills_json.length})
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {activeScore.missing_secondary_skills_json.map((s) => (
                          <span key={s} className="rounded bg-amber-500/15 px-1.5 py-0.5 text-xs text-amber-300">
                            {s}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Cross-Resume Bullet Alerts */}
                  {activeScore.cross_resume_alerts_json.length > 0 && (
                    <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
                      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-amber-300">
                        <AlertTriangle className="h-4 w-4" />
                        Cross-Resume Bullet Alert ({activeScore.cross_resume_alerts_json.length})
                      </div>
                      <div className="space-y-2 text-xs">
                        {activeScore.cross_resume_alerts_json.map((al, i) => (
                          <div key={i} className="rounded border border-amber-500/20 bg-slate-950/70 p-2.5">
                            <div className="font-medium text-amber-200">
                              Requirement: {al.jd_requirement}
                            </div>
                            <div className="mt-1 text-slate-300">
                              Verified proof exists in <strong className="text-white">{al.other_resume_track}</strong> (
                              {al.other_resume_pdf}) — {Math.round(al.similarity * 100)}% match:
                            </div>
                            <div className="mt-1 italic text-emerald-300">“{al.matching_bullet}”</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Option 3 Bullet Proof Table */}
                  <div className="overflow-hidden rounded-lg border border-slate-800">
                    <table className="w-full text-left text-xs">
                      <thead className="bg-slate-950 text-slate-400">
                        <tr>
                          <th className="px-3 py-2">Status</th>
                          <th className="px-3 py-2">JD Requirement</th>
                          <th className="px-3 py-2">Verbatim Resume Proof ({activeScore.pdf_filename})</th>
                          <th className="px-3 py-2 text-right">Sim</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800">
                        {activeScore.bullet_proof_json.map((row, i) => (
                          <tr key={i} className="bg-slate-900/50">
                            <td className="px-3 py-2 align-top whitespace-nowrap">
                              {row.status === 'MATCHED' ? (
                                <span className="inline-flex items-center gap-1 text-emerald-400">
                                  <CheckCircle2 className="h-3.5 w-3.5" /> MATCHED
                                </span>
                              ) : (
                                <span className="inline-flex items-center gap-1 text-rose-400">
                                  <XCircle className="h-3.5 w-3.5" /> GAP
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2 align-top text-slate-200">{row.jd_requirement}</td>
                            <td className="px-3 py-2 align-top text-slate-300">
                              {row.matched_bullet ?? <span className="italic text-slate-500">No direct bullet match</span>}
                            </td>
                            <td className="px-3 py-2 align-top text-right font-mono text-slate-400">
                              {Math.round(row.similarity * 100)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          )}

          {!loading && detail && activeTab === 'diff' && (
            <div className="space-y-4">
              {detail.sibling_jobs.length === 0 ? (
                <p className="text-sm text-slate-400">No sibling roles linked at {detail.company_name}.</p>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs text-slate-400">Compare against sibling:</span>
                    {detail.sibling_jobs.map((sib) => (
                      <button
                        key={sib.id}
                        onClick={() => handleSelectSibling(sib.id)}
                        className={`rounded border px-2.5 py-1 text-xs ${
                          selectedSiblingId === sib.id
                            ? 'border-sky-500 bg-sky-500/20 text-sky-200'
                            : 'border-slate-700 text-slate-300 hover:bg-slate-800'
                        }`}
                      >
                        #{sib.id} {sib.role_subtag} {sib.req_id ? `(${sib.req_id})` : ''}
                      </button>
                    ))}
                  </div>

                  {diff && (
                    <div className="space-y-4">
                      <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-4 text-xs">
                        <div className="font-semibold text-white">
                          Similarity: {diff.similarity_pct}% — {diff.job_a_subtag} vs. {diff.job_b_subtag}
                        </div>
                        <div className="mt-2 flex flex-wrap gap-4">
                          <div>
                            <span className="text-rose-400">Only in this role:</span>{' '}
                            {diff.only_in_job_a_skills.join(', ') || 'None'}
                          </div>
                          <div>
                            <span className="text-emerald-400">Only in sibling:</span>{' '}
                            {diff.only_in_job_b_skills.join(', ') || 'None'}
                          </div>
                        </div>
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-3">
                          <h4 className="mb-2 text-xs font-semibold text-rose-300">
                            Unique to #{diff.job_a_id} ({diff.removed_lines.length})
                          </h4>
                          <ul className="space-y-1 text-xs text-slate-300">
                            {diff.removed_lines.map((line, i) => (
                              <li key={i}>- {line}</li>
                            ))}
                          </ul>
                        </div>
                        <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-3">
                          <h4 className="mb-2 text-xs font-semibold text-emerald-300">
                            Unique to Sibling #{diff.job_b_id} ({diff.added_lines.length})
                          </h4>
                          <ul className="space-y-1 text-xs text-slate-300">
                            {diff.added_lines.map((line, i) => (
                              <li key={i}>+ {line}</li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {!loading && detail && activeTab === 'jd' && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-400">
                  {showRawJd ? 'Raw Scraped JD' : 'Boilerplate-Stripped JD'}
                </span>
                <button
                  onClick={() => setShowRawJd((v) => !v)}
                  className="rounded border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                >
                  Show {showRawJd ? 'Cleaned JD' : 'Raw JD'}
                </button>
              </div>
              <pre className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-950 p-4 text-xs leading-relaxed text-slate-200">
                {showRawJd ? detail.description_raw : detail.boilerplate_stripped_text || detail.description_raw}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

