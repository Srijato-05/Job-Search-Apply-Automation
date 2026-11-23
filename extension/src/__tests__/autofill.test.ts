import { describe, expect, it, vi } from 'vitest';
import { ALL_ADAPTER_NAMES, getAdapterForPortal } from '../content/adapters';
import type { QARuleItem, VaultFacts } from '../content/adapters/types';
import {
  isSubmitLikeControl,
  selectNativeOrAriaOption,
  withAutoSubmitShield,
} from '../content/dom_engine';

function parseHtml(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

const SAMPLE_VAULT: VaultFacts = {
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
  tenth_pct: 94.2,
  twelfth_pct: 92.5,
};

const SAMPLE_RULES: QARuleItem[] = [
  {
    normalized_question: 'are you comfortable with relocation',
    canonical_aliases_json: ['willing to relocate', 'open to relocate'],
    verified_answer: 'Yes, comfortable relocating to Bengaluru.',
  },
];

describe('Cycle 7 Deterministic Autofill Engine & 13 Portal Adapters', () => {
  it('registers all 13 isolated adapters with fallback', () => {
    expect(ALL_ADAPTER_NAMES).toHaveLength(13);
    expect(ALL_ADAPTER_NAMES).toEqual(
      expect.arrayContaining([
        'greenhouse',
        'lever',
        'ashby',
        'smartrecruiters',
        'workday',
        'naukri',
        'linkedin',
        'indeed',
        'instahyre',
        'foundit',
        'hirist',
        'cutshort',
        'generic',
      ]),
    );
  });

  it('fills Greenhouse React inputs, attaches DataTransfer PDF, blocks PII, highlights unknowns Amber, and NEVER auto-clicks submit', () => {
    const doc = parseHtml(`
      <form id="application_form">
        <label for="first_name">First Name</label>
        <input id="first_name" type="text" />

        <label for="last_name">Last Name</label>
        <input id="last_name" type="text" />

        <label for="email">Email</label>
        <input id="email" type="email" />

        <label for="pan">PAN Card Number</label>
        <input id="pan" type="text" />

        <label for="dob">Date of Birth</label>
        <input id="dob" type="text" />

        <label for="custom_q">Why do you want to join Razorpay?</label>
        <textarea id="custom_q"></textarea>

        <label for="resume">Resume/CV</label>
        <input id="resume" type="file" />

        <button id="submit_app" type="submit">Submit Application</button>
      </form>
    `);

    const submitSpy = vi.fn();
    doc.getElementById('submit_app')!.addEventListener('click', submitSpy);

    const report = getAdapterForPortal('greenhouse').run({
      document: doc,
      pageUrl: 'https://boards.greenhouse.io/razorpay/jobs/101',
      vault: SAMPLE_VAULT,
      qaRules: SAMPLE_RULES,
      resumePdf: { filename: 'Aarav_Backend.pdf', bytes: [37, 80, 68, 70] },
    });

    expect(report.adapterName).toBe('greenhouse');
    expect(report.pausedBeforeSubmit).toBe(true);
    expect(submitSpy).not.toHaveBeenCalled();

    // Vault values filled via native setter
    expect((doc.getElementById('first_name') as HTMLInputElement).value).toBe('Aarav');
    expect((doc.getElementById('last_name') as HTMLInputElement).value).toBe('Sharma');
    expect((doc.getElementById('email') as HTMLInputElement).value).toBe('aarav@example.com');

    // Resume PDF attached via DataTransfer
    const fileInput = doc.getElementById('resume') as HTMLInputElement;
    expect(report.resumeAttached).toBe(true);
    expect(fileInput.files?.[0]?.name).toBe('Aarav_Backend.pdf');

    // Sensitive PII blocked
    expect((doc.getElementById('pan') as HTMLInputElement).value).toBe('');
    expect((doc.getElementById('dob') as HTMLInputElement).value).toBe('');
    expect(report.blockedPiiFields).toEqual(['PAN Card Number', 'Date of Birth']);

    // Unknown question flagged in Amber for Pause-and-Learn
    const customQ = doc.getElementById('custom_q') as HTMLTextAreaElement;
    expect(customQ.getAttribute('data-jobautomation-amber')).toBe('true');
    expect(report.unknownFields).toEqual([
      { question: 'Why do you want to join Razorpay?', fieldTag: 'textarea' },
    ]);
  });

  it('handles Workday multi-entry select/inputs and LinkedIn Easy Apply without auto-submit', () => {
    const wdDoc = parseHtml(`
      <div data-automation-id="jobApplication">
        <label for="wd_ctc">Expected CTC (LPA)</label>
        <input id="wd_ctc" type="text" />

        <label for="wd_reloc">Willing to relocate</label>
        <select id="wd_reloc">
          <option value="">-- Select --</option>
          <option value="yes">Yes, comfortable relocating to Bengaluru.</option>
        </select>

        <input data-automation-id="file-upload-input-ref" type="file" aria-label="Resume" />
        <button type="submit">Submit</button>
      </div>
    `);
    const wdReport = getAdapterForPortal('workday').run({
      document: wdDoc,
      pageUrl: 'https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal/job/1',
      vault: SAMPLE_VAULT,
      qaRules: SAMPLE_RULES,
      resumePdf: { filename: 'Aarav_Backend.pdf', bytes: [37, 80, 68, 70] },
    });

    expect((wdDoc.getElementById('wd_ctc') as HTMLInputElement).value).toBe('32');
    expect((wdDoc.getElementById('wd_reloc') as HTMLSelectElement).value).toBe('yes');
    expect(wdReport.resumeAttached).toBe(true);

    const liDoc = parseHtml(`
      <div class="jobs-easy-apply-modal">
        <label for="li_phone">Mobile phone number</label>
        <input id="li_phone" type="tel" />
        <label for="li_notice">Notice Period (days)</label>
        <input id="li_notice" type="number" />
        <button aria-label="Submit application">Submit application</button>
      </div>
    `);
    const liReport = getAdapterForPortal('linkedin').run({
      document: liDoc,
      pageUrl: 'https://www.linkedin.com/jobs/view/123/',
      vault: SAMPLE_VAULT,
      qaRules: SAMPLE_RULES,
    });
    expect((liDoc.getElementById('li_phone') as HTMLInputElement).value).toBe('+91-9876543210');
    expect((liDoc.getElementById('li_notice') as HTMLInputElement).value).toBe('30');
    expect(liReport.pausedBeforeSubmit).toBe(true);
  });

  it('fills Naukri Chatbot drawer prompts and highlights unknown bot questions in Amber', () => {
    const knownChatDoc = parseHtml(`
      <div class="chatbot_Drawer">
        <div class="botMsg"><span>What is your Current CTC in LPA?</span></div>
        <div class="chatbot_InputContainer"><input class="chatbot_Input" type="text" /></div>
      </div>
    `);
    const r1 = getAdapterForPortal('naukri').run({
      document: knownChatDoc,
      pageUrl: 'https://www.naukri.com/job-listings-1',
      vault: SAMPLE_VAULT,
      qaRules: SAMPLE_RULES,
    });
    expect((knownChatDoc.querySelector('.chatbot_Input') as HTMLInputElement).value).toBe('22');
    expect(r1.filledFields).toContain('What is your Current CTC in LPA?');

    const unknownChatDoc = parseHtml(`
      <div class="chatbot_Drawer">
        <div class="botMsg"><span>Have you ever worked with Apache Flink in banking?</span></div>
        <div class="chatbot_InputContainer"><input class="chatbot_Input" type="text" /></div>
      </div>
    `);
    const r2 = getAdapterForPortal('naukri').run({
      document: unknownChatDoc,
      pageUrl: 'https://www.naukri.com/job-listings-2',
      vault: SAMPLE_VAULT,
      qaRules: SAMPLE_RULES,
    });
    expect(unknownChatDoc.querySelector('.chatbot_Input')?.getAttribute('data-jobautomation-amber')).toBe('true');
    expect(r2.unknownFields[0].fieldTag).toBe('chatbot');
  });

  it('enforces multi-layer anti-autosubmit failsafes (isSubmitLikeControl + capture-phase submit shield)', () => {
    const doc = parseHtml(`
      <form id="hostile_form">
        <button id="b1" type="submit">Submit</button>
        <button id="b2" type="button">Apply now</button>
        <button id="b3" type="button" aria-label="Send Application">Send</button>
        <button id="b4" type="button">Cancel</button>
      </form>
    `);

    expect(isSubmitLikeControl(doc.getElementById('b1'))).toBe(true);
    expect(isSubmitLikeControl(doc.getElementById('b2'))).toBe(true);
    expect(isSubmitLikeControl(doc.getElementById('b3'))).toBe(true);
    expect(isSubmitLikeControl(doc.getElementById('b4'))).toBe(false);

    // selectNativeOrAriaOption refuses to click submit controls
    const b2ClickSpy = vi.fn();
    doc.getElementById('b2')!.addEventListener('click', b2ClickSpy);
    expect(selectNativeOrAriaOption(doc, doc.getElementById('b2')!, 'Apply now')).toBe(false);
    expect(b2ClickSpy).not.toHaveBeenCalled();

    // Capture-phase submit shield cancels programmatic form submits while autofill runs,
    // and unhooks cleanly afterwards so the human can submit manually
    const form = doc.getElementById('hostile_form') as HTMLFormElement;
    const submitHandler = vi.fn();
    form.addEventListener('submit', submitHandler);

    withAutoSubmitShield(doc, () => {
      const ev = new Event('submit', { bubbles: true, cancelable: true });
      form.dispatchEvent(ev);
      expect(ev.defaultPrevented).toBe(true);
    });
    expect(submitHandler).not.toHaveBeenCalled();

    // After shield lifts, manual user submission works normally
    const manualEv = new Event('submit', { bubbles: true, cancelable: true });
    form.dispatchEvent(manualEv);
    expect(submitHandler).toHaveBeenCalledTimes(1);
  });
});

