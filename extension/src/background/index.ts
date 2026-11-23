const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000';
const STORAGE_KEY_TOKEN = 'localToken';
const STORAGE_KEY_URL = 'backendUrl';

interface ExtensionSettings {
  localToken: string;
  backendUrl: string;
}

async function loadSettings(): Promise<ExtensionSettings> {
  const stored = await chrome.storage.local.get([STORAGE_KEY_TOKEN, STORAGE_KEY_URL]);
  return {
    localToken: String(stored[STORAGE_KEY_TOKEN] ?? ''),
    backendUrl: String(stored[STORAGE_KEY_URL] ?? DEFAULT_BACKEND_URL).replace(/\/+$/, ''),
  };
}

async function callBackendApi(
  path: string,
  method = 'GET',
  body?: unknown,
): Promise<{ ok: boolean; status: number; data?: unknown; error?: string }> {
  const { localToken, backendUrl } = await loadSettings();
  const headers: Record<string, string> = {};
  if (localToken) {
    headers['X-Local-Token'] = localToken;
  }
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const res = await fetch(`${backendUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    const text = await res.text();
    let parsed: unknown = null;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = text;
    }
    if (!res.ok) {
      const detail =
        typeof parsed === 'object' && parsed !== null && 'detail' in parsed
          ? String((parsed as { detail: unknown }).detail)
          : `HTTP ${res.status}`;
      return { ok: false, status: res.status, error: detail };
    }
    return { ok: true, status: res.status, data: parsed };
  } catch (err) {
    return {
      ok: false,
      status: 0,
      error: `Backend unreachable at ${backendUrl}: ${(err as Error).message}`,
    };
  }
}

async function fetchResumePdfBytes(
  resumeId: number,
  fallbackFilename = 'resume.pdf',
): Promise<{ ok: boolean; bytes?: number[]; filename?: string; error?: string }> {
  const { localToken, backendUrl } = await loadSettings();
  const headers: Record<string, string> = {};
  if (localToken) {
    headers['X-Local-Token'] = localToken;
  }

  try {
    const res = await fetch(`${backendUrl}/api/v1/resumes/${resumeId}/file`, { headers });
    if (!res.ok) {
      return { ok: false, error: `Failed to fetch PDF (${res.status})` };
    }
    const buf = await res.arrayBuffer();
    const disposition = res.headers.get('content-disposition') ?? '';
    const m = disposition.match(/filename="?([^"]+)"?/i);
    return {
      ok: true,
      bytes: Array.from(new Uint8Array(buf)),
      filename: m?.[1] || fallbackFilename,
    };
  } catch (err) {
    return { ok: false, error: (err as Error).message };
  }
}

async function handleLifecycleEvent(message: {
  event?: { type: string };
  context?: Record<string, unknown>;
}) {
  const evType = message.event?.type;
  const ctx = message.context;
  if (!evType || !ctx) return;

  const check = await callBackendApi('/api/v1/extension/check-page', 'POST', ctx);
  if (!check.ok || !check.data || typeof check.data !== 'object') return;
  const data = check.data as {
    job_id?: number | null;
    application_id?: number | null;
    company_slug?: string;
    winning_score?: { resume_id?: number } | null;
    banner_state?: string;
  };

  if (evType === 'EXPIRED_DETECTED' && data.job_id) {
    await callBackendApi(`/api/v1/jobs/${data.job_id}/status`, 'PATCH', { status: 'closed' });
    return;
  }

  if (
    (evType === 'CONFIRMATION_SEEN' || evType === 'NATIVE_APPLIED_DETECTED') &&
    data.banner_state !== 'ALREADY_APPLIED'
  ) {
    let appId = data.application_id ?? null;
    if (!appId && (data.job_id || data.company_slug)) {
      const draft = await callBackendApi('/api/v1/applications/draft', 'POST', {
        job_id: data.job_id ?? undefined,
        company_slug: data.company_slug || undefined,
        resume_id: data.winning_score?.resume_id ?? undefined,
        portal_used: String(ctx.portal_name ?? 'extension'),
        detection_method: evType.toLowerCase(),
      });
      if (draft.ok && draft.data && typeof draft.data === 'object') {
        appId = (draft.data as { id?: number }).id ?? null;
      }
    }
    if (appId) {
      await callBackendApi(`/api/v1/applications/${appId}/submit`, 'POST', {
        detection_method: evType.toLowerCase(),
        portal_used: String(ctx.portal_name ?? 'extension'),
        jd_snapshot_text: String(ctx.description_raw ?? ''),
      });
    }
  }
}

if (chrome.sidePanel?.setPanelBehavior) {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'API_REQUEST') {
    callBackendApi(message.path, message.method, message.body).then(sendResponse);
    return true;
  }

  if (message?.type === 'FETCH_RESUME_PDF') {
    fetchResumePdfBytes(Number(message.resumeId), message.filename).then(sendResponse);
    return true;
  }

  if (message?.type === 'GET_SETTINGS') {
    loadSettings().then(sendResponse);
    return true;
  }

  if (message?.type === 'SAVE_SETTINGS') {
    chrome.storage.local
      .set({
        [STORAGE_KEY_TOKEN]: String(message.localToken ?? '').trim(),
        [STORAGE_KEY_URL]: String(message.backendUrl ?? DEFAULT_BACKEND_URL).trim(),
      })
      .then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message?.type === 'PAGE_LIFECYCLE_EVENT') {
    handleLifecycleEvent(message).then(() => sendResponse({ ok: true }));
    return true;
  }

  return false;
});

