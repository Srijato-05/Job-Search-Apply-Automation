import { detectAtsFromUrl } from '../shared/ats_detector';

const bannerBox = document.getElementById('bannerBox')!;
const bannerTitle = document.getElementById('bannerTitle')!;
const bannerMsg = document.getElementById('bannerMsg')!;
const tabPortal = document.getElementById('tabPortal')!;
const resumeCard = document.getElementById('resumeCard')!;
const resumeText = document.getElementById('resumeText')!;
const cooldownCard = document.getElementById('cooldownCard')!;
const cooldownText = document.getElementById('cooldownText')!;
const diffCard = document.getElementById('diffCard')!;
const diffText = document.getElementById('diffText')!;
const autofillBtn = document.getElementById('autofillBtn')!;
const amberLearnCard = document.getElementById('amberLearnCard')!;
const amberFieldsList = document.getElementById('amberFieldsList')!;
const watchAtsBtn = document.getElementById('watchAtsBtn')!;
const captureJobsBtn = document.getElementById('captureJobsBtn')!;
const refreshBtn = document.getElementById('refreshBtn')!;
const statusLog = document.getElementById('statusLog')!;
const toggleSettingsBtn = document.getElementById('toggleSettingsBtn')!;
const settingsPanel = document.getElementById('settingsPanel') as HTMLFormElement;
const tokenInput = document.getElementById('tokenInput') as HTMLInputElement;
const urlInput = document.getElementById('urlInput') as HTMLInputElement;

let latestCheckData: {
  job_id?: number | null;
  company_slug?: string;
  banner_state?: string;
  winning_score?: { resume_id?: number; pdf_filename?: string; track_name?: string; tier?: string; semantic_bullet_coverage_pct?: number } | null;
} | null = null;
let latestPageContext: Record<string, unknown> = {};

async function getActiveTab(): Promise<chrome.tabs.Tab | null> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab ?? null;
}

function sendBg<T>(msg: Record<string, unknown>): Promise<T> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(msg, (res) => resolve(res as T));
  });
}

function sendTab<T>(tabId: number, msg: Record<string, unknown>): Promise<T | null> {
  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (res) => {
      if (chrome.runtime.lastError) {
        resolve(null);
      } else {
        resolve((res as T) ?? null);
      }
    });
  });
}

async function refreshSidePanel() {
  statusLog.textContent = '';
  const tab = await getActiveTab();
  const tabUrl = tab?.url ?? '';
  tabPortal.textContent = tabUrl ? new URL(tabUrl).hostname : 'No active tab';

  // Show "+ Watch Company ATS" if on Greenhouse/Lever/Ashby/SmartRecruiters/Workday
  const detectedAts = tabUrl ? detectAtsFromUrl(tabUrl) : null;
  if (detectedAts) {
    watchAtsBtn.classList.remove('hidden');
    watchAtsBtn.textContent = `+ Watch ${detectedAts.display_name} (${detectedAts.ats_type})`;
    watchAtsBtn.onclick = async () => {
      const res = await sendBg<{ ok: boolean; error?: string }>({
        type: 'API_REQUEST',
        method: 'POST',
        path: '/api/v1/watchlist',
        body: { ...detectedAts, employer_type: 'direct_product', is_watched: true },
      });
      statusLog.textContent = res.ok
        ? `Added ${detectedAts.display_name} to automated ATS watchlist.`
        : `Error: ${res.error}`;
    };
  } else {
    watchAtsBtn.classList.add('hidden');
  }

  let context: Record<string, unknown> = {
    page_url: tabUrl,
    title: tab?.title ?? '',
  };
  let signals: { nativeApplied?: boolean; expired?: boolean } = {};

  if (tab?.id) {
    const tabRes = await sendTab<{
      ok: boolean;
      context?: Record<string, unknown>;
      signals?: { nativeApplied?: boolean; expired?: boolean };
    }>(tab.id, { type: 'GET_PAGE_CONTEXT' });
    if (tabRes?.ok && tabRes.context) {
      context = tabRes.context;
      signals = tabRes.signals ?? {};
    }
  }

  const check = await sendBg<{
    ok: boolean;
    error?: string;
    data?: {
      banner_state: string;
      message: string;
      job_id?: number | null;
      company_slug?: string;
      winning_score?: {
        resume_id?: number;
        pdf_filename?: string;
        track_name: string;
        tier: string;
        semantic_bullet_coverage_pct: number;
      } | null;
      cooldown?: { apps_last_30d: number; max_company_apps_30d: number; warning_message?: string | null };
      sibling_diff?: { similarity_pct: number; only_in_job_b_skills: string[] } | null;
    };
  }>({
    type: 'API_REQUEST',
    method: 'POST',
    path: '/api/v1/extension/check-page',
    body: context,
  });

  latestPageContext = context;
  latestCheckData = check.data ?? null;

  if (!check.ok || !check.data) {
    bannerBox.className = 'banner STARTED_BUT_NOT_SUBMITTED';
    bannerTitle.textContent = 'Connect Local Backend';
    bannerMsg.textContent = check.error || 'Verify backend & X-Local-Token in Token settings.';
    return;
  }

  const d = check.data;
  bannerBox.className = `banner ${d.banner_state}`;
  bannerTitle.textContent = signals.expired
    ? `${d.banner_state} (PORTAL EXPIRED)`
    : signals.nativeApplied
      ? `${d.banner_state} (Applied badge seen)`
      : d.banner_state.replace(/_/g, ' ');
  bannerMsg.textContent = d.message;

  if (d.winning_score) {
    resumeCard.classList.remove('hidden');
    resumeText.textContent = `${d.winning_score.track_name} — Tier ${d.winning_score.tier} (${d.winning_score.semantic_bullet_coverage_pct}%)`;
  } else {
    resumeCard.classList.add('hidden');
  }

  if (d.cooldown) {
    cooldownCard.classList.remove('hidden');
    cooldownText.textContent = `${d.cooldown.apps_last_30d}/${d.cooldown.max_company_apps_30d} submitted in 30d${
      d.cooldown.warning_message ? ` — ${d.cooldown.warning_message}` : ''
    }`;
  } else {
    cooldownCard.classList.add('hidden');
  }

  if (d.sibling_diff) {
    diffCard.classList.remove('hidden');
    diffText.textContent = `Similarity ${d.sibling_diff.similarity_pct}% | Unique skills: ${
      d.sibling_diff.only_in_job_b_skills.join(', ') || 'None'
    }`;
  } else {
    diffCard.classList.add('hidden');
  }
}

async function executeAutofill() {
  const tab = await getActiveTab();
  if (!tab?.id) return;

  statusLog.textContent = 'Fetching verified Fact Vault & Q&A rules…';
  const [vaultRes, qaRes] = await Promise.all([
    sendBg<{ ok: boolean; data?: unknown }>({ type: 'API_REQUEST', method: 'GET', path: '/api/v1/vault' }),
    sendBg<{ ok: boolean; data?: unknown[] }>({
      type: 'API_REQUEST',
      method: 'GET',
      path: '/api/v1/vault/qa-rules',
    }),
  ]);

  if (!vaultRes.ok || !vaultRes.data) {
    statusLog.textContent = 'Cannot load Fact Vault. Verify backend & token.';
    return;
  }

  // Record Draft (autofill_started_at) only if not already submitted
  if (latestCheckData?.banner_state !== 'ALREADY_APPLIED' && (latestCheckData?.job_id || latestCheckData?.company_slug)) {
    await sendBg({
      type: 'API_REQUEST',
      method: 'POST',
      path: '/api/v1/applications/draft',
      body: {
        job_id: latestCheckData.job_id ?? undefined,
        company_slug: latestCheckData.company_slug || undefined,
        resume_id: latestCheckData.winning_score?.resume_id ?? undefined,
        portal_used: String(latestPageContext.portal_name ?? 'extension'),
        detection_method: 'extension_autofill',
      },
    });
  }

  let resumePdf: unknown = null;
  const winResumeId = latestCheckData?.winning_score?.resume_id;
  if (winResumeId) {
    const pdfRes = await sendBg<{ ok: boolean; bytes?: number[]; filename?: string }>({
      type: 'FETCH_RESUME_PDF',
      resumeId: winResumeId,
      filename: latestCheckData?.winning_score?.pdf_filename || 'resume.pdf',
    });
    if (pdfRes.ok && pdfRes.bytes) {
      resumePdf = { filename: pdfRes.filename || 'resume.pdf', bytes: pdfRes.bytes };
    }
  }

  const runRes = await sendTab<{
    ok: boolean;
    report?: {
      adapterName: string;
      filledFields: string[];
      blockedPiiFields: string[];
      unknownFields: { question: string; fieldTag: string }[];
      resumeAttached: boolean;
    };
  }>(tab.id, {
    type: 'RUN_AUTOFILL',
    vault: vaultRes.data,
    qaRules: qaRes.data ?? [],
    resumePdf,
  });

  if (!runRes?.ok || !runRes.report) {
    statusLog.textContent = 'No form detected on active tab (reload page if extension just updated).';
    return;
  }

  const rep = runRes.report;
  statusLog.textContent = `Autofilled ${rep.filledFields.length} field(s) via ${rep.adapterName}${
    rep.resumeAttached ? ' + PDF attached' : ''
  }. MANUAL REVIEW REQUIRED: Verify all fields & PDF, then click Submit yourself.${
    rep.blockedPiiFields.length ? ` Blocked PII: ${rep.blockedPiiFields.join(', ')}.` : ''
  }`;

  if (rep.unknownFields.length > 0) {
    amberLearnCard.classList.remove('hidden');
    amberFieldsList.innerHTML = '';
    rep.unknownFields.forEach((uf) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;flex-direction:column;gap:4px;';
      const lbl = document.createElement('div');
      lbl.className = 'muted';
      lbl.textContent = uf.question;
      const inp = document.createElement('input');
      inp.placeholder = 'Verified answer (blocked for PAN/Aadhaar/DoB)';
      const saveBtn = document.createElement('button');
      saveBtn.className = 'warn';
      saveBtn.type = 'button';
      saveBtn.textContent = 'Save Q&A Rule & Refill';
      saveBtn.onclick = async () => {
        if (!inp.value.trim()) return;
        const saveRes = await sendBg<{ ok: boolean; error?: string }>({
          type: 'API_REQUEST',
          method: 'POST',
          path: '/api/v1/vault/qa-rules',
          body: { question: uf.question, verified_answer: inp.value.trim() },
        });
        if (!saveRes.ok) {
          statusLog.textContent = `Blocked/Error: ${saveRes.error}`;
          return;
        }
        await executeAutofill();
      };
      row.append(lbl, inp, saveBtn);
      amberFieldsList.appendChild(row);
    });
  } else {
    amberLearnCard.classList.add('hidden');
  }
}

autofillBtn.addEventListener('click', () => {
  executeAutofill();
});

captureJobsBtn.addEventListener('click', async () => {
  const tab = await getActiveTab();
  if (!tab?.id) return;
  const harvested = await sendTab<{ ok: boolean; jobs?: unknown[] }>(tab.id, {
    type: 'HARVEST_VISIBLE_JOBS',
  });
  const jobs = harvested?.jobs ?? [];
  if (jobs.length === 0) {
    statusLog.textContent = 'No harvestable job cards detected on this tab.';
    return;
  }
  const ingest = await sendBg<{ ok: boolean; data?: unknown[]; error?: string }>({
    type: 'API_REQUEST',
    method: 'POST',
    path: '/api/v1/jobs/ingest',
    body: { jobs },
  });
  statusLog.textContent = ingest.ok
    ? `Captured & scored ${jobs.length} visible job(s) into local queue.`
    : `Ingest error: ${ingest.error}`;
});

refreshBtn.addEventListener('click', () => {
  refreshSidePanel();
});

toggleSettingsBtn.addEventListener('click', () => {
  settingsPanel.classList.toggle('hidden');
  settingsPanel.style.display = settingsPanel.classList.contains('hidden') ? 'none' : 'flex';
});

settingsPanel.addEventListener('submit', async (e) => {
  e.preventDefault();
  await sendBg({
    type: 'SAVE_SETTINGS',
    localToken: tokenInput.value,
    backendUrl: urlInput.value || 'http://127.0.0.1:8000',
  });
  settingsPanel.classList.add('hidden');
  settingsPanel.style.display = 'none';
  refreshSidePanel();
});

sendBg<{ localToken: string; backendUrl: string }>({ type: 'GET_SETTINGS' }).then((cfg) => {
  tokenInput.value = cfg?.localToken ?? '';
  urlInput.value = cfg?.backendUrl ?? 'http://127.0.0.1:8000';
  refreshSidePanel();
});

