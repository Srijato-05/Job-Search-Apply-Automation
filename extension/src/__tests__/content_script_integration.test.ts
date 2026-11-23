import { beforeEach, describe, expect, it, vi } from 'vitest';

describe('Content Script Message Handlers (GET_PAGE_CONTEXT, HARVEST_VISIBLE_JOBS, RUN_AUTOFILL)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it('wires chrome.runtime.onMessage and handles GET_PAGE_CONTEXT, HARVEST_VISIBLE_JOBS, and RUN_AUTOFILL safely', async () => {
    let listener:
      | ((msg: unknown, sender: unknown, sendResponse: (res: unknown) => void) => boolean)
      | null = null;
    const sendMessageSpy = vi.fn();

    vi.stubGlobal('chrome', {
      runtime: {
        onMessage: {
          addListener: vi.fn((fn) => {
            listener = fn;
          }),
        },
        sendMessage: sendMessageSpy,
      },
    });

    // Set URL & realistic Greenhouse posting + form DOM
    Object.defineProperty(window, 'location', {
      value: new URL('https://boards.greenhouse.io/razorpay/jobs/4242'),
      writable: true,
    });
    document.body.innerHTML = `
      <main>
        <h1 class="app-title">Senior Backend Engineer</h1>
        <span class="company-name">Razorpay</span>
        <span class="location">Bengaluru, India</span>
        <div id="content">Build Python and FastAPI microservices.</div>
        <form id="application_form">
          <label for="f_email">Email</label>
          <input id="f_email" type="email" />
          <label for="f_pan">PAN Card</label>
          <input id="f_pan" type="text" />
          <label for="f_why">Notice Negotiable Details</label>
          <textarea id="f_why"></textarea>
          <label for="f_res">Resume</label>
          <input id="f_res" type="file" />
          <button id="btn_sub" type="submit">Submit Application</button>
        </form>
      </main>
    `;
    const submitSpy = vi.fn();
    document.getElementById('btn_sub')!.addEventListener('click', submitSpy);

    await import('../content/index');
    expect(listener).not.toBeNull();

    // 1. GET_PAGE_CONTEXT
    let ctxResp: Record<string, unknown> = {};
    expect(listener!({ type: 'GET_PAGE_CONTEXT' }, {}, (r) => { ctxResp = r as Record<string, unknown>; })).toBe(true);
    expect(ctxResp.ok).toBe(true);
    expect(ctxResp.context).toMatchObject({
      title: 'Senior Backend Engineer',
      company_name: 'Razorpay',
      portal_name: 'greenhouse',
      external_job_id: '4242',
    });

    // 2. RUN_AUTOFILL via content script message
    let fillResp: { ok?: boolean; report?: Record<string, unknown> } = {};
    expect(
      listener!(
        {
          type: 'RUN_AUTOFILL',
          vault: {
            full_name: 'Aarav Sharma',
            email: 'aarav@example.in',
            phone: '+91-9876543210',
            linkedin_url: '',
            github_url: '',
            portfolio_url: '',
            current_ctc_lpa: 22,
            expected_ctc_lpa: 32,
            notice_period_days: 30,
            total_exp_years: 4.5,
            current_city: 'Bengaluru',
          },
          qaRules: [],
          resumePdf: { filename: 'Aarav.pdf', bytes: [37, 80, 68, 70] },
        },
        {},
        (r) => {
          fillResp = r as { ok?: boolean; report?: Record<string, unknown> };
        },
      ),
    ).toBe(true);

    expect(fillResp.ok).toBe(true);
    expect(fillResp.report?.adapterName).toBe('greenhouse');
    expect(fillResp.report?.pausedBeforeSubmit).toBe(true);
    expect(fillResp.report?.resumeAttached).toBe(true);
    expect(fillResp.report?.blockedPiiFields).toEqual(['PAN Card']);
    expect((document.getElementById('f_email') as HTMLInputElement).value).toBe('aarav@example.in');
    expect(document.getElementById('f_why')!.getAttribute('data-jobautomation-amber')).toBe('true');
    expect(submitSpy).not.toHaveBeenCalled();

    // 3. HARVEST_VISIBLE_JOBS
    Object.defineProperty(window, 'location', {
      value: new URL('https://www.naukri.com/python-jobs'),
      writable: true,
    });
    document.body.innerHTML = `
      <div class="srp-jobtuple-wrapper" data-job-id="nk-9">
        <a class="title" href="/job-listings-9">Backend Engineer</a>
        <a class="comp-name">CRED</a>
        <span class="locWdth">Bengaluru</span>
      </div>
    `;
    let harvestResp: { ok?: boolean; jobs?: unknown[] } = {};
    expect(listener!({ type: 'HARVEST_VISIBLE_JOBS' }, {}, (r) => { harvestResp = r as { ok?: boolean; jobs?: unknown[] }; })).toBe(true);
    expect(harvestResp.ok).toBe(true);
    expect(harvestResp.jobs).toHaveLength(1);

    // Unknown message returns false
    expect(listener!({ type: 'UNKNOWN_MSG' }, {}, () => {})).toBe(false);
  });
});

