import { beforeEach, describe, expect, it, vi } from 'vitest';
import { resolveFactAnswer, resolveLearnedQaAnswer } from '../content/adapters/generic_heuristic';
import type { QARuleItem, VaultFacts } from '../content/adapters/types';
import { selectNativeOrAriaOption } from '../content/dom_engine';

describe('Fact/Q&A Resolvers, ARIA Select & Background Message Routing', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it('resolveFactAnswer covers all Indian field synonyms, single/multi-part names, and empty/zero optional values', () => {
    const fullVault: VaultFacts = {
      full_name: 'Aarav Kumar Sharma',
      email: 'aarav@example.in',
      phone: '+91-9876543210',
      linkedin_url: 'https://linkedin.com/in/aarav',
      github_url: 'https://github.com/aarav',
      portfolio_url: 'https://aarav.dev',
      current_ctc_lpa: 18,
      expected_ctc_lpa: 28,
      notice_period_days: 30,
      total_exp_years: 4.5,
      current_city: 'Bengaluru',
      tenth_pct: 95,
      twelfth_pct: 92,
    };

    expect(resolveFactAnswer('First Name', fullVault)).toBe('Aarav');
    expect(resolveFactAnswer('Surname *', fullVault)).toBe('Kumar Sharma');
    expect(resolveFactAnswer('Name*', fullVault)).toBe('Aarav Kumar Sharma');
    expect(resolveFactAnswer('Personal site', fullVault)).toBe('https://aarav.dev');
    expect(resolveFactAnswer('Current compensation (LPA)', fullVault)).toBe('18');
    expect(resolveFactAnswer('eCTC', fullVault)).toBe('28');
    expect(resolveFactAnswer('Days to join', fullVault)).toBe('30');
    expect(resolveFactAnswer('Relevant experience (years)', fullVault)).toBe('4.5');
    expect(resolveFactAnswer('SSC Marks %', fullVault)).toBe('95');
    expect(resolveFactAnswer('HSC Percentage', fullVault)).toBe('92');

    // Single-word name & zero/missing optionals return null cleanly
    const sparseVault: VaultFacts = {
      full_name: 'Cher',
      email: '',
      phone: '',
      linkedin_url: '',
      github_url: '',
      portfolio_url: '',
      current_ctc_lpa: 0,
      expected_ctc_lpa: 0,
      notice_period_days: 0,
      total_exp_years: 0,
      current_city: '',
      tenth_pct: null,
      twelfth_pct: null,
    };
    expect(resolveFactAnswer('First Name', sparseVault)).toBe('Cher');
    expect(resolveFactAnswer('Last Name', sparseVault)).toBeNull();
    expect(resolveFactAnswer('Current CTC', sparseVault)).toBeNull();
    expect(resolveFactAnswer('10th Percentage', sparseVault)).toBeNull();
  });

  it('resolveLearnedQaAnswer normalizes punctuation and matches aliases accurately', () => {
    const rules: QARuleItem[] = [
      {
        normalized_question: 'are you comfortable working in rotational shifts',
        canonical_aliases_json: ['24x7 support shifts', 'rotational shifts ok'],
        verified_answer: 'No, prefer day shifts.',
      },
    ];
    expect(resolveLearnedQaAnswer('  Are you comfortable working in rotational shifts?! ', rules)).toBe(
      'No, prefer day shifts.',
    );
    expect(resolveLearnedQaAnswer('Are you OK with 24x7 support shifts?', rules)).toBe('No, prefer day shifts.');
    expect(resolveLearnedQaAnswer('   ', rules)).toBeNull();
    expect(resolveLearnedQaAnswer('Unrelated random question', rules)).toBeNull();
  });

  it('selectNativeOrAriaOption handles native <select> matching and safe ARIA [role="option"] clicks', () => {
    const doc = new DOMParser().parseFromString(
      `
        <div>
          <select id="sel">
            <option value="">-- Choose --</option>
            <option value="bengaluru_in">Bengaluru, Karnataka</option>
          </select>
          <div id="combo" role="combobox"></div>
          <ul role="listbox">
            <li id="opt1" role="option">Immediate (0 days)</li>
            <li id="opt2" role="option">30 Days Notice</li>
          </ul>
        </div>
      `,
      'text/html',
    );

    expect(selectNativeOrAriaOption(doc, doc.getElementById('sel')!, 'bengaluru')).toBe(true);
    expect((doc.getElementById('sel') as HTMLSelectElement).value).toBe('bengaluru_in');
    expect(selectNativeOrAriaOption(doc, doc.getElementById('sel')!, 'nonexistent-city')).toBe(false);
    expect(selectNativeOrAriaOption(doc, doc.getElementById('sel')!, '   ')).toBe(false);

    const opt2Spy = vi.fn();
    doc.getElementById('opt2')!.addEventListener('click', opt2Spy);
    expect(selectNativeOrAriaOption(doc, doc.getElementById('combo')!, '30 days')).toBe(true);
    expect(opt2Spy).toHaveBeenCalledTimes(1);
  });

  it('Background Service Worker routes API_REQUEST, FETCH_RESUME_PDF, PAGE_LIFECYCLE_EVENT, and offline errors', async () => {
    let messageHandler:
      | ((msg: unknown, sender: unknown, sendResponse: (resp: unknown) => void) => boolean)
      | null = null;

    const storageData: Record<string, string> = {
      localToken: 'tok-bg-1',
      backendUrl: 'http://127.0.0.1:8000',
    };

    vi.stubGlobal('chrome', {
      storage: {
        local: {
          get: vi.fn(async () => storageData),
          set: vi.fn(async (obj: Record<string, string>) => {
            Object.assign(storageData, obj);
          }),
        },
      },
      sidePanel: {
        setPanelBehavior: vi.fn(async () => undefined),
      },
      runtime: {
        onMessage: {
          addListener: vi.fn((fn) => {
            messageHandler = fn;
          }),
        },
      },
    });

    const fetchMock = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      const u = String(url);
      if (u.endsWith('/api/v1/resumes/5/file')) {
        return {
          ok: true,
          status: 200,
          arrayBuffer: async () => new Uint8Array([37, 80, 68, 70]).buffer,
          headers: new Headers({ 'content-disposition': 'attachment; filename="Aarav_Go.pdf"' }),
        } as unknown as Response;
      }
      if (u.endsWith('/api/v1/extension/check-page')) {
        return {
          ok: true,
          status: 200,
          text: async () =>
            JSON.stringify({
              job_id: 99,
              application_id: null,
              company_slug: 'razorpay',
              banner_state: 'NEW_ROLE',
              winning_score: { resume_id: 5 },
            }),
        } as Response;
      }
      if (u.endsWith('/api/v1/applications/draft')) {
        return { ok: true, status: 201, text: async () => JSON.stringify({ id: 77 }) } as Response;
      }
      if (u.endsWith('/api/v1/applications/77/submit')) {
        return { ok: true, status: 200, text: async () => JSON.stringify({ id: 77, stage: 'applied' }) } as Response;
      }
      if (u.includes('/offline')) {
        throw new TypeError('Failed to fetch');
      }
      return {
        ok: true,
        status: 200,
        text: async () => JSON.stringify({ method: init?.method ?? 'GET' }),
      } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    await import('../background/index');
    expect(messageHandler).not.toBeNull();

    const invoke = (msg: unknown) =>
      new Promise<Record<string, unknown>>((resolve) => {
        messageHandler!(msg, {}, (resp) => resolve(resp as Record<string, unknown>));
      });

    // 1. Offline error mapped safely to status: 0
    const offlineResp = await invoke({ type: 'API_REQUEST', path: '/offline', method: 'GET' });
    expect(offlineResp.ok).toBe(false);
    expect(offlineResp.status).toBe(0);
    expect(String(offlineResp.error)).toContain('Backend unreachable');

    // 2. FETCH_RESUME_PDF extracts bytes & filename header
    const pdfResp = await invoke({ type: 'FETCH_RESUME_PDF', resumeId: 5 });
    expect(pdfResp.ok).toBe(true);
    expect(pdfResp.filename).toBe('Aarav_Go.pdf');
    expect(pdfResp.bytes).toEqual([37, 80, 68, 70]);

    // 3. CONFIRMATION_SEEN automatically drafts + marks submitted
    await invoke({
      type: 'PAGE_LIFECYCLE_EVENT',
      event: { type: 'CONFIRMATION_SEEN' },
      context: { portal_name: 'greenhouse', description_raw: 'Payments JD' },
    });
    const calledUrls = fetchMock.mock.calls.map((c) => String(c[0]));
    expect(calledUrls.some((u) => u.endsWith('/api/v1/applications/draft'))).toBe(true);
    expect(calledUrls.some((u) => u.endsWith('/api/v1/applications/77/submit'))).toBe(true);
  });
});

