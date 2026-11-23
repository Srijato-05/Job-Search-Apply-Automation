import type {
  AnalyticsSummary,
  ApplicationRecord,
  CollectorHealthResponse,
  CollectorProgress,
  CooldownStatus,
  FactVaultData,
  JobCard,
  JobDetail,
  JobDiffResponse,
  JobListResponse,
  QARuleItem,
  ResumeDetail,
  ResumeSummary,
  WatchedCompany,
  WatchlistVerifyResponse,
} from './types';

declare global {
  interface Window {
    __JOB_AUTOMATION_TOKEN__?: string;
  }
}

const TOKEN_STORAGE_KEY = 'job_automation_local_token';

export function getLocalToken(): string {
  if (typeof window !== 'undefined') {
    if (window.__JOB_AUTOMATION_TOKEN__) {
      return window.__JOB_AUTOMATION_TOKEN__;
    }
    const stored = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (stored) {
      return stored;
    }
  }
  const envToken = (import.meta as unknown as { env?: Record<string, string> }).env?.VITE_LOCAL_TOKEN;
  return envToken || '';
}

export function setLocalToken(token: string): void {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token.trim());
    window.__JOB_AUTOMATION_TOKEN__ = token.trim();
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getLocalToken();
  if (token) {
    headers.set('X-Local-Token', token);
  }
  if (!(init.body instanceof FormData) && !headers.has('Content-Type') && init.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const errBody = await res.json();
      detail = errBody?.detail || JSON.stringify(errBody);
    } catch {
      // ignore non-json error bodies
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export interface JobQueryParams {
  tier?: string;
  resume_id?: number;
  fresh_6h?: boolean;
  missing_max?: number;
  friction?: string;
  city?: string;
  fts_query?: string;
  only_hidden?: boolean;
  job_status?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}

export const api = {
  // Jobs
  listJobs(params: JobQueryParams = {}): Promise<JobListResponse> {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== '' && v !== false) {
        qs.set(k, String(v));
      } else if (typeof v === 'boolean' && v === true) {
        qs.set(k, 'true');
      }
    });
    const q = qs.toString();
    return apiFetch<JobListResponse>(`/api/v1/jobs${q ? `?${q}` : ''}`);
  },
  getJobDetail(jobId: number): Promise<JobDetail> {
    return apiFetch<JobDetail>(`/api/v1/jobs/${jobId}`);
  },
  getJobDiff(jobId: number, siblingId: number): Promise<JobDiffResponse> {
    return apiFetch<JobDiffResponse>(`/api/v1/jobs/${jobId}/diff/${siblingId}`);
  },
  updateJobStatus(
    jobId: number,
    payload: { status?: string; hidden_by_gate1?: boolean; hidden_reason?: string | null },
  ): Promise<JobCard> {
    return apiFetch<JobCard>(`/api/v1/jobs/${jobId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },
  rescoreJobs(): Promise<{ rescored_count: number }> {
    return apiFetch<{ rescored_count: number }>('/api/v1/jobs/rescore', { method: 'POST' });
  },

  // Applications & Cooldowns
  listApplications(stage?: string): Promise<ApplicationRecord[]> {
    const qs = stage && stage !== 'all' ? `?stage=${encodeURIComponent(stage)}` : '';
    return apiFetch<ApplicationRecord[]>(`/api/v1/applications${qs}`);
  },
  startDraft(payload: {
    job_id?: number;
    company_slug?: string;
    resume_id?: number;
    portal_used?: string;
    detection_method?: string;
  }): Promise<ApplicationRecord> {
    return apiFetch<ApplicationRecord>('/api/v1/applications/draft', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  submitApplication(
    appId: number,
    payload: { resume_id?: number; recruiter_notes?: string } = {},
  ): Promise<ApplicationRecord> {
    return apiFetch<ApplicationRecord>(`/api/v1/applications/${appId}/submit`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  updateApplication(
    appId: number,
    payload: { stage?: string; recruiter_notes?: string },
  ): Promise<ApplicationRecord> {
    return apiFetch<ApplicationRecord>(`/api/v1/applications/${appId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },
  getCooldown(companySlug: string): Promise<CooldownStatus> {
    return apiFetch<CooldownStatus>(`/api/v1/applications/cooldown/${encodeURIComponent(companySlug)}`);
  },
  getAnalytics(): Promise<AnalyticsSummary> {
    return apiFetch<AnalyticsSummary>('/api/v1/applications/analytics');
  },

  // Fact Vault & Q&A
  getVault(): Promise<FactVaultData> {
    return apiFetch<FactVaultData>('/api/v1/vault');
  },
  updateVault(payload: FactVaultData): Promise<FactVaultData> {
    return apiFetch<FactVaultData>('/api/v1/vault', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
  },
  listQaRules(): Promise<QARuleItem[]> {
    return apiFetch<QARuleItem[]>('/api/v1/vault/qa-rules');
  },
  createQaRule(payload: {
    question: string;
    verified_answer: string;
    answer_type?: string;
    portal_scope?: string;
  }): Promise<QARuleItem> {
    return apiFetch<QARuleItem>('/api/v1/vault/qa-rules', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  deleteQaRule(ruleId: number): Promise<void> {
    return apiFetch<void>(`/api/v1/vault/qa-rules/${ruleId}`, { method: 'DELETE' });
  },

  // Resumes
  listResumes(): Promise<ResumeSummary[]> {
    return apiFetch<ResumeSummary[]>('/api/v1/resumes');
  },
  getResumeDetail(resumeId: number): Promise<ResumeDetail> {
    return apiFetch<ResumeDetail>(`/api/v1/resumes/${resumeId}`);
  },
  uploadResume(formData: FormData): Promise<ResumeDetail> {
    return apiFetch<ResumeDetail>('/api/v1/resumes', {
      method: 'POST',
      body: formData,
    });
  },
  reparseResume(resumeId: number): Promise<ResumeDetail> {
    return apiFetch<ResumeDetail>(`/api/v1/resumes/${resumeId}/reparse`, { method: 'POST' });
  },
  deleteResume(resumeId: number): Promise<void> {
    return apiFetch<void>(`/api/v1/resumes/${resumeId}`, { method: 'DELETE' });
  },

  // Collectors & Watchlist
  listWatchlist(): Promise<WatchedCompany[]> {
    return apiFetch<WatchedCompany[]>('/api/v1/watchlist?watched_only=false');
  },
  addCompany(payload: {
    slug: string;
    display_name: string;
    employer_type: string;
    ats_type: string;
    ats_config_json: Record<string, unknown>;
    is_watched: boolean;
  }): Promise<WatchedCompany> {
    return apiFetch<WatchedCompany>('/api/v1/watchlist', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
  toggleWatchCompany(slug: string, is_watched: boolean): Promise<WatchedCompany> {
    return apiFetch<WatchedCompany>(`/api/v1/watchlist/${encodeURIComponent(slug)}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_watched }),
    });
  },
  verifyWatchlist(): Promise<WatchlistVerifyResponse> {
    return apiFetch<WatchlistVerifyResponse>('/api/v1/watchlist/verify', { method: 'POST' });
  },
  getCollectorHealth(): Promise<CollectorHealthResponse> {
    return apiFetch<CollectorHealthResponse>('/api/v1/collectors/health');
  },
  getCollectorProgress(): Promise<CollectorProgress> {
    return apiFetch<CollectorProgress>('/api/v1/collectors/progress');
  },
  getSchedulerStatus(): Promise<{ running: boolean; interval_hours: number }> {
    return apiFetch<{ running: boolean; interval_hours: number }>('/api/v1/collectors/scheduler');
  },
  startScheduler(): Promise<{ running: boolean; interval_hours: number }> {
    return apiFetch<{ running: boolean; interval_hours: number }>('/api/v1/collectors/scheduler/start', {
      method: 'POST',
    });
  },
  stopScheduler(): Promise<{ running: boolean; interval_hours: number }> {
    return apiFetch<{ running: boolean; interval_hours: number }>('/api/v1/collectors/scheduler/stop', {
      method: 'POST',
    });
  },
  runCollectors(
    source: string,
    opts: { background?: boolean; force?: boolean; hours_old?: number } = {},
  ): Promise<unknown> {
    const bg = opts.background ? '?background=true' : '';
    return apiFetch(`/api/v1/collectors/run${bg}`, {
      method: 'POST',
      body: JSON.stringify({
        source,
        force: Boolean(opts.force),
        hours_old: opts.hours_old ?? 24,
      }),
    });
  },

  // Backup Export & Restore
  async downloadBackupZip(): Promise<Blob> {
    const headers = new Headers();
    const token = getLocalToken();
    if (token) headers.set('X-Local-Token', token);
    const res = await fetch('/api/v1/backup/export', { headers });
    if (!res.ok) throw new ApiError(res.status, `Backup export failed (${res.status})`);
    return await res.blob();
  },
  restoreBackupZip(file: File): Promise<{ status: string; message: string }> {
    const fd = new FormData();
    fd.append('file', file);
    return apiFetch<{ status: string; message: string }>('/api/v1/backup/restore', {
      method: 'POST',
      body: fd,
    });
  },
};

