import { beforeEach, describe, expect, it, vi } from 'vitest';

const SIDEPANEL_HTML = `
  <div class="wrap">
    <div id="tabPortal">Inspecting active tab…</div>
    <button id="toggleSettingsBtn" type="button">Token</button>
    <form id="settingsPanel" class="hidden">
      <input id="tokenInput" type="password" />
      <input id="urlInput" type="text" />
      <button id="saveSettingsBtn" type="submit">Save Connection</button>
    </form>
    <div id="bannerBox" class="banner NEW_ROLE">
      <strong id="bannerTitle">Checking page…</strong>
      <div id="bannerMsg"></div>
    </div>
    <div id="resumeCard" class="hidden"><div id="resumeText"></div></div>
    <div id="cooldownCard" class="hidden"><div id="cooldownText"></div></div>
    <div id="diffCard" class="hidden"><div id="diffText"></div></div>
    <div>
      <button id="autofillBtn" type="button">Autofill Form (Pause at Submit)</button>
      <button id="refreshBtn" type="button">Refresh Page Check</button>
      <button id="watchAtsBtn" class="hidden" type="button">+ Watch Company ATS</button>
      <button id="captureJobsBtn" type="button">Capture Visible Jobs</button>
      <div id="statusLog"></div>
    </div>
    <div id="amberLearnCard" class="hidden">
      <div id="amberFieldsList"></div>
    </div>
  </div>
`;

function loadSidePanelDom() {
  document.body.innerHTML = SIDEPANEL_HTML;
}

describe('Extension Side Panel UI Orchestration (4-State Banner, +Watch ATS, Autofill & Pause-and-Learn)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
    loadSidePanelDom();
  });

  it('renders NEW_SIBLING_ROLE banner, Watch ATS button, Autofill, and Pause-and-Learn Q&A flow without auto-submit', async () => {
    const bgCalls: Record<string, unknown>[] = [];
    const tabCalls: Record<string, unknown>[] = [];

    let qaRuleSaved = false;

    vi.stubGlobal('chrome', {
      tabs: {
        query: vi.fn(async () => [
          { id: 42, url: 'https://boards.greenhouse.io/razorpay/jobs/9002', title: 'SDE II' },
        ]),
        sendMessage: vi.fn((_tabId: number, msg: Record<string, unknown>, cb: (res: unknown) => void) => {
          tabCalls.push(msg);
          if (msg.type === 'GET_PAGE_CONTEXT') {
            cb({
              ok: true,
              context: {
                page_url: 'https://boards.greenhouse.io/razorpay/jobs/9002',
                title: 'SDE II',
                company_name: 'Razorpay',
                portal_name: 'greenhouse',
                description_raw: 'React and TypeScript frontend team.',
              },
              signals: { nativeApplied: false, expired: false },
            });
            return;
          }
          if (msg.type === 'RUN_AUTOFILL') {
            cb({
              ok: true,
              report: {
                adapterName: 'greenhouse',
                filledFields: ['Email', 'Resume PDF'],
                blockedPiiFields: ['PAN Card'],
                unknownFields: qaRuleSaved
                  ? []
                  : [{ question: 'Notice period negotiable?', fieldTag: 'input' }],
                resumeAttached: true,
              },
            });
            return;
          }
          if (msg.type === 'HARVEST_VISIBLE_JOBS') {
            cb({ ok: true, jobs: [] });
          }
        }),
      },
      runtime: {
        lastError: null,
        sendMessage: vi.fn((msg: Record<string, unknown>, cb: (res: unknown) => void) => {
          bgCalls.push(msg);
          if (msg.type === 'GET_SETTINGS') {
            cb({ localToken: 'tok-sp', backendUrl: 'http://127.0.0.1:8000' });
            return;
          }
          if (msg.type === 'FETCH_RESUME_PDF') {
            cb({ ok: true, bytes: [37, 80, 68, 70], filename: 'Aarav_FS.pdf' });
            return;
          }
          if (msg.type === 'API_REQUEST') {
            if (msg.path === '/api/v1/extension/check-page') {
              cb({
                ok: true,
                data: {
                  banner_state: 'NEW_SIBLING_ROLE',
                  message: 'Separate sibling opening at Razorpay.',
                  job_id: 202,
                  company_slug: 'razorpay',
                  winning_score: {
                    resume_id: 2,
                    pdf_filename: 'Aarav_FS.pdf',
                    track_name: 'FullStack Web',
                    tier: 'S',
                    semantic_bullet_coverage_pct: 91,
                  },
                  cooldown: { apps_last_30d: 1, max_company_apps_30d: 3, warning_message: null },
                  sibling_diff: { similarity_pct: 28, only_in_job_b_skills: ['React', 'TypeScript'] },
                },
              });
              return;
            }
            if (msg.path === '/api/v1/vault') {
              cb({ ok: true, data: { full_name: 'Aarav', email: 'a@example.in' } });
              return;
            }
            if (msg.path === '/api/v1/vault/qa-rules' && msg.method === 'POST') {
              qaRuleSaved = true;
              cb({ ok: true, data: { id: 1 } });
              return;
            }
            if (msg.path === '/api/v1/vault/qa-rules') {
              cb({ ok: true, data: [] });
              return;
            }
            cb({ ok: true, data: { id: 88 } });
            return;
          }
          cb({ ok: true });
        }),
      },
    });

    await import('../sidepanel/main');

    // Wait for initial check-page hydration
    await vi.waitFor(() => {
      expect(document.getElementById('bannerTitle')!.textContent).toBe('NEW SIBLING ROLE');
    });

    expect(document.getElementById('bannerBox')!.className).toContain('NEW_SIBLING_ROLE');
    expect(document.getElementById('resumeText')!.textContent).toContain('FullStack Web — Tier S (91%)');
    expect(document.getElementById('cooldownText')!.textContent).toContain('1/3 submitted in 30d');
    expect(document.getElementById('diffText')!.textContent).toContain('React, TypeScript');

    // + Watch Company ATS button populated for Greenhouse
    const watchBtn = document.getElementById('watchAtsBtn') as HTMLButtonElement;
    expect(watchBtn.classList.contains('hidden')).toBe(false);
    expect(watchBtn.textContent).toContain('Razorpay (greenhouse)');
    watchBtn.click();
    await vi.waitFor(() => {
      expect(document.getElementById('statusLog')!.textContent).toContain('Added Razorpay');
    });

    // Click Autofill -> creates Draft -> attaches PDF -> displays MANUAL REVIEW REQUIRED + Amber field
    (document.getElementById('autofillBtn') as HTMLButtonElement).click();
    await vi.waitFor(() => {
      expect(document.getElementById('statusLog')!.textContent).toContain('MANUAL REVIEW REQUIRED');
    });
    expect(document.getElementById('statusLog')!.textContent).toContain('Blocked PII: PAN Card');
    expect(document.getElementById('amberLearnCard')!.classList.contains('hidden')).toBe(false);

    // Pause-and-Learn: enter answer and click Save Q&A Rule & Refill
    const amberInput = document.querySelector('#amberFieldsList input') as HTMLInputElement;
    const amberSaveBtn = document.querySelector('#amberFieldsList button') as HTMLButtonElement;
    amberInput.value = 'Yes, up to 15 days';
    amberSaveBtn.click();

    await vi.waitFor(() => {
      expect(qaRuleSaved).toBe(true);
      expect(document.getElementById('amberLearnCard')!.classList.contains('hidden')).toBe(true);
    });
    expect(bgCalls.some((c) => c.path === '/api/v1/applications/draft')).toBe(true);
    expect(tabCalls.filter((c) => c.type === 'RUN_AUTOFILL')).toHaveLength(2);
  });

  it('shows Connect Local Backend fallback when backend is unreachable', async () => {
    vi.stubGlobal('chrome', {
      tabs: {
        query: vi.fn(async () => [{ id: 1, url: 'https://www.naukri.com/job-1', title: 'Job' }]),
        sendMessage: vi.fn((_id: number, _msg: unknown, cb: (r: unknown) => void) => cb(null)),
      },
      runtime: {
        lastError: { message: 'No receiver' },
        sendMessage: vi.fn((msg: Record<string, unknown>, cb: (r: unknown) => void) => {
          if (msg.type === 'GET_SETTINGS') {
            cb({ localToken: '', backendUrl: 'http://127.0.0.1:8000' });
            return;
          }
          cb({ ok: false, error: 'Backend unreachable at http://127.0.0.1:8000' });
        }),
      },
    });

    await import('../sidepanel/main');

    await vi.waitFor(() => {
      expect(document.getElementById('bannerTitle')!.textContent).toBe('Connect Local Backend');
    });
    expect(document.getElementById('bannerMsg')!.textContent).toContain('Backend unreachable');
  });
});
