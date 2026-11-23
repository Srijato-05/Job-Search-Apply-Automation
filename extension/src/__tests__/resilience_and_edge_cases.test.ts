import { describe, expect, it, vi } from 'vitest';
import { getAdapterForPortal } from '../content/adapters';
import type { VaultFacts } from '../content/adapters/types';
import { attachResumePdf, extractFieldLabel } from '../content/dom_engine';
import { harvestVisibleJobs } from '../content/harvester';
import {
  attachSubmitWatcher,
  detectConfirmationScreen,
  detectExpiredPosting,
  detectNativeAppliedBadge,
} from '../content/submit_watcher';

function parseHtml(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

const VAULT: VaultFacts = {
  full_name: 'Aarav Sharma',
  email: 'aarav@example.com',
  phone: '+91-9876543210',
  linkedin_url: 'https://linkedin.com/in/aarav',
  github_url: 'https://github.com/aarav',
  portfolio_url: 'https://aarav.dev',
  current_ctc_lpa: 22,
  expected_ctc_lpa: 32,
  notice_period_days: 30,
  total_exp_years: 4.5,
  current_city: 'Bengaluru',
};

describe('Extension Hostile DOM, Crash-Free Fallbacks & Resilience Tests', () => {
  it('skips disabled, readonly, hidden, reset, image inputs and leaves pre-filled user answers untouched', () => {
    const doc = parseHtml(`
      <form>
        <label for="f_dis">Email</label>
        <input id="f_dis" type="email" disabled />

        <label for="f_ro">Full Name</label>
        <input id="f_ro" type="text" readonly />

        <label for="f_hid">Phone</label>
        <input id="f_hid" type="hidden" value="keep-hidden" />

        <label for="f_custom">Why do you want this role?</label>
        <textarea id="f_custom">User already typed a custom answer</textarea>

        <input type="reset" value="Reset Form" />
        <input type="image" alt="Submit Application" />
      </form>
    `);

    const report = getAdapterForPortal('generic').run({
      document: doc,
      pageUrl: 'https://company.com/apply',
      vault: VAULT,
      qaRules: [],
    });

    expect((doc.getElementById('f_dis') as HTMLInputElement).value).toBe('');
    expect((doc.getElementById('f_ro') as HTMLInputElement).value).toBe('');
    expect((doc.getElementById('f_hid') as HTMLInputElement).value).toBe('keep-hidden');
    expect((doc.getElementById('f_custom') as HTMLTextAreaElement).value).toBe('User already typed a custom answer');
    expect(doc.getElementById('f_custom')!.getAttribute('data-jobautomation-amber')).toBeNull();
    expect(report.unknownFields).toEqual([]);
  });

  it('extractFieldLabel handles special CSS characters in id, broken aria-labelledby, and wrapping labels without throwing', () => {
    const doc = parseHtml(`
      <form>
        <label for="field:1.2[0]">Email</label>
        <input id="field:1.2[0]" type="email" />

        <input id="broken_aria" aria-labelledby="nonexistent-1 nonexistent-2" placeholder="Notice Period" />

        <label>Current City <input id="wrapped" type="text" /></label>
      </form>
    `);

    expect(extractFieldLabel(doc, doc.getElementById('field:1.2[0]')!)).toBe('Email');
    expect(extractFieldLabel(doc, doc.getElementById('broken_aria')!)).toBe('Notice Period');
    expect(extractFieldLabel(doc, doc.getElementById('wrapped')!)).toBe('Current City');
  });

  it('attachResumePdf succeeds even when global DataTransfer is unavailable (fallback path)', () => {
    const doc = parseHtml(`<input id="res" type="file" />`);
    const input = doc.getElementById('res') as HTMLInputElement;
    const changeSpy = vi.fn();
    input.addEventListener('change', changeSpy);

    const origDT = globalThis.DataTransfer;
    // @ts-expect-error simulating missing DataTransfer in restricted DOM
    globalThis.DataTransfer = undefined;
    try {
      const ok = attachResumePdf(input, { filename: 'Fallback.pdf', bytes: [37, 80, 68, 70] });
      expect(ok).toBe(true);
      expect(input.files?.[0]?.name).toBe('Fallback.pdf');
      expect(changeSpy).toHaveBeenCalledTimes(1);
    } finally {
      globalThis.DataTransfer = origDT;
    }
  });

  it('harvestVisibleJobs safely ignores incomplete cards and unsupported portals without throwing', () => {
    const emptyDoc = parseHtml(`<div><div class="srp-jobtuple-wrapper"></div></div>`);
    expect(harvestVisibleJobs(emptyDoc, 'https://www.naukri.com/jobs')).toEqual([]);
    expect(harvestVisibleJobs(emptyDoc, 'https://unknown-site.example/jobs')).toEqual([]);

    const partialCardDoc = parseHtml(`
      <div class="srp-jobtuple-wrapper">
        <a class="title" href="javascript:void(0)">Title Only Without Company</a>
      </div>
    `);
    expect(harvestVisibleJobs(partialCardDoc, 'https://www.naukri.com/jobs')).toEqual([]);
  });

  it('SubmitWatcher accurately distinguishes expired, confirmation, and applied badges without false positives', () => {
    // Normal active JD mentioning "submitted code" or "closed loop" must NOT false-trigger!
    const normalDoc = parseHtml(`
      <main>
        <h1>Senior Backend Engineer</h1>
        <p>Join our team building closed-loop payment systems and submitting telemetry.</p>
        <button type="button">Apply now</button>
      </main>
    `);
    expect(detectExpiredPosting(normalDoc)).toBe(false);
    expect(detectConfirmationScreen(normalDoc)).toBe(false);
    expect(detectNativeAppliedBadge(normalDoc)).toBe(false);

    // Explicit expired and initial applied badges fire once cleanly
    const expiredDoc = parseHtml(`
      <body>
        <div class="closed-job">Position has been filled</div>
        <div data-applied="true">Already applied</div>
      </body>
    `);
    const events: string[] = [];
    const detach = attachSubmitWatcher(expiredDoc, (ev) => events.push(ev.type));
    expect(events).toEqual(['EXPIRED_DETECTED', 'NATIVE_APPLIED_DETECTED']);
    detach();
  });
});

