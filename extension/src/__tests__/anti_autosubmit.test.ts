import { describe, expect, it, vi } from 'vitest';
import { ALL_ADAPTER_NAMES, getAdapterForPortal } from '../content/adapters';
import type { VaultFacts } from '../content/adapters/types';
import {
  isSubmitLikeControl,
  selectNativeOrAriaOption,
  withAutoSubmitShield,
} from '../content/dom_engine';

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

describe('Anti-Autosubmit Multi-Layer Failsafe Stress Tests', () => {
  it('detects all submit-like control patterns (type=submit, ancestor submit, ARIA, id, name, text)', () => {
    const doc = parseHtml(`
      <form>
        <button id="s1" type="submit">Save &amp; Continue</button>
        <input id="s2" type="submit" value="Go" />
        <button id="s3" type="submit"><span id="s3_icon" class="icon-send"></span></button>
        <div id="s4" role="button" aria-label="Confirm and Submit Application"></div>
        <button id="s5" type="button">Apply Now</button>
        <button id="s6" type="button">Easy Apply</button>
        <button id="s7" type="button">Send Application</button>
        <button id="s8" type="button" data-automation-id="bottom-navigation-next-button" name="final_submit">Continue</button>
        <button id="s9" type="button">Complete Application</button>
        <button id="s10" type="button">Finish Application</button>

        <button id="safe_next" type="button">Next</button>
        <button id="safe_cancel" type="button">Cancel</button>
        <input id="safe_text" type="text" />
      </form>
    `);

    for (const id of ['s1', 's2', 's3', 's3_icon', 's4', 's5', 's6', 's7', 's8', 's9', 's10']) {
      expect(isSubmitLikeControl(doc.getElementById(id)), `Expected #${id} to be submit-like`).toBe(true);
    }

    expect(isSubmitLikeControl(null)).toBe(false);
    expect(isSubmitLikeControl(undefined)).toBe(false);
    expect(isSubmitLikeControl(doc.getElementById('safe_next'))).toBe(false);
    expect(isSubmitLikeControl(doc.getElementById('safe_cancel'))).toBe(false);
    expect(isSubmitLikeControl(doc.getElementById('safe_text'))).toBe(false);
  });

  it('selectNativeOrAriaOption refuses submit-like triggers and submit-like ARIA options', () => {
    const doc = parseHtml(`
      <div>
        <button id="fake_combo" type="button" aria-label="Submit application">Choose</button>
        <div id="aria_combo" role="combobox">
          <div role="option">Submit Application</div>
          <div role="option">Yes - Immediate Joiner</div>
        </div>
      </div>
    `);

    const fakeClick = vi.fn();
    doc.getElementById('fake_combo')!.addEventListener('click', fakeClick);
    expect(selectNativeOrAriaOption(doc, doc.getElementById('fake_combo')!, 'Choose')).toBe(false);
    expect(fakeClick).not.toHaveBeenCalled();

    // Even if target searches for "submit application", ARIA option with submit text must NOT be clicked
    const submitOptClick = vi.fn();
    doc.querySelectorAll('[role="option"]')[0].addEventListener('click', submitOptClick);
    expect(selectNativeOrAriaOption(doc, doc.getElementById('aria_combo')!, 'submit application')).toBe(false);
    expect(submitOptClick).not.toHaveBeenCalled();
  });

  it('withAutoSubmitShield blocks hostile change-triggered submit() AND submit-button clicks, then restores manual control', () => {
    const doc = parseHtml(`
      <form id="hostile">
        <label for="email">Email</label>
        <input id="email" type="email" />
        <button id="btn_apply" type="submit">Apply Now</button>
        <button id="btn_safe" type="button">Preview</button>
      </form>
    `);
    const form = doc.getElementById('hostile') as HTMLFormElement;
    const submitSpy = vi.fn();
    const applyClickSpy = vi.fn();
    const safeClickSpy = vi.fn();

    form.addEventListener('submit', submitSpy);
    doc.getElementById('btn_apply')!.addEventListener('click', applyClickSpy);
    doc.getElementById('btn_safe')!.addEventListener('click', safeClickSpy);

    // Hostile page JS attempts to auto-submit when email input fires 'change'
    doc.getElementById('email')!.addEventListener('change', () => {
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      (doc.getElementById('btn_apply') as HTMLButtonElement).click();
      (doc.getElementById('btn_safe') as HTMLButtonElement).click();
    });

    const report = getAdapterForPortal('greenhouse').run({
      document: doc,
      pageUrl: 'https://boards.greenhouse.io/razorpay/jobs/1',
      vault: VAULT,
      qaRules: [],
    });

    expect(report.pausedBeforeSubmit).toBe(true);
    expect((doc.getElementById('email') as HTMLInputElement).value).toBe('aarav@example.com');
    expect(submitSpy).not.toHaveBeenCalled();
    expect(applyClickSpy).not.toHaveBeenCalled();
    expect(safeClickSpy).toHaveBeenCalledTimes(1);

    // Confirm even direct nested shield invocation returns fn value and cleans up on throw
    expect(() =>
      withAutoSubmitShield(doc, () => {
        throw new Error('simulated error');
      }),
    ).toThrow('simulated error');

    // After shield unwinds, human user CAN click Apply and trigger form submission normally
    (doc.getElementById('btn_apply') as HTMLButtonElement).click();
    expect(applyClickSpy).toHaveBeenCalledTimes(1);
    expect(submitSpy).toHaveBeenCalledTimes(1);
  });

  it('never clicks Next, Continue, or Submit buttons across ALL 13 adapters', () => {
    for (const adapterName of ALL_ADAPTER_NAMES) {
      const doc = parseHtml(`
        <form>
          <label for="f_email">Email</label>
          <input id="f_email" type="email" />
          <button id="next_btn" type="button">Next</button>
          <button id="continue_btn" type="button">Continue</button>
          <button id="submit_btn" type="submit">Submit Application</button>
        </form>
      `);
      const nextSpy = vi.fn();
      const continueSpy = vi.fn();
      const submitSpy = vi.fn();
      doc.getElementById('next_btn')!.addEventListener('click', nextSpy);
      doc.getElementById('continue_btn')!.addEventListener('click', continueSpy);
      doc.getElementById('submit_btn')!.addEventListener('click', submitSpy);

      const report = getAdapterForPortal(adapterName).run({
        document: doc,
        pageUrl: 'https://example.com/apply',
        vault: VAULT,
        qaRules: [],
      });

      expect(report.pausedBeforeSubmit, `${adapterName} must pauseBeforeSubmit`).toBe(true);
      expect(nextSpy, `${adapterName} must not click Next`).not.toHaveBeenCalled();
      expect(continueSpy, `${adapterName} must not click Continue`).not.toHaveBeenCalled();
      expect(submitSpy, `${adapterName} must not click Submit`).not.toHaveBeenCalled();
    }
  });
});
