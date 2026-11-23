import { describe, expect, it, vi } from 'vitest';
import { getAdapterForPortal } from '../content/adapters';
import type { QARuleItem, VaultFacts } from '../content/adapters/types';

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
  tenth_pct: 94.2,
  twelfth_pct: 91.5,
};

const RULES: QARuleItem[] = [
  {
    normalized_question: 'work authorization in india',
    canonical_aliases_json: ['authorized to work in india'],
    verified_answer: 'Yes',
  },
];

describe('Multi-Page Wizard Workflow & Selective File Attachment', () => {
  it('handles multi-step wizard (abc -> Next -> def+PDF/img -> Next -> ghi+Submit) safely per page without clicking Next/Submit', () => {
    const adapter = getAdapterForPortal('workday');

    // === STEP 1: Basic Info ("abc -> next") ===
    const step1Doc = parseHtml(`
      <div data-automation-id="jobApplication">
        <label for="s1_name">Full Name</label>
        <input id="s1_name" type="text" />
        <label for="s1_email">Email</label>
        <input id="s1_email" type="email" />
        <button id="s1_next" type="button">Next</button>
      </div>
    `);
    const s1NextSpy = vi.fn();
    step1Doc.getElementById('s1_next')!.addEventListener('click', s1NextSpy);

    const r1 = adapter.run({
      document: step1Doc,
      pageUrl: 'https://company.wd5.myworkdayjobs.com/careers/apply/step1',
      vault: VAULT,
      qaRules: RULES,
    });
    expect((step1Doc.getElementById('s1_name') as HTMLInputElement).value).toBe('Aarav Sharma');
    expect((step1Doc.getElementById('s1_email') as HTMLInputElement).value).toBe('aarav@example.com');
    expect(s1NextSpy).not.toHaveBeenCalled();
    expect(r1.pausedBeforeSubmit).toBe(true);

    // User manually clicks Next -> Portal transitions DOM to Step 2
    // === STEP 2: Documents ("def + document/pdf/img -> next") ===
    const step2Doc = parseHtml(`
      <div data-automation-id="jobApplication">
        <label for="s2_photo">Passport Size Photo</label>
        <input id="s2_photo" type="file" accept="image/png, image/jpeg" />

        <label for="s2_cover">Cover Letter (Optional)</label>
        <input id="s2_cover" type="file" accept=".pdf,.doc" />

        <label for="s2_resume">Upload Resume / CV</label>
        <input id="s2_resume" type="file" accept=".pdf" />

        <label for="s2_ctc">Current CTC (LPA)</label>
        <input id="s2_ctc" type="text" />

        <button id="s2_next" type="button">Next</button>
      </div>
    `);
    const s2NextSpy = vi.fn();
    step2Doc.getElementById('s2_next')!.addEventListener('click', s2NextSpy);

    const r2 = adapter.run({
      document: step2Doc,
      pageUrl: 'https://company.wd5.myworkdayjobs.com/careers/apply/step2',
      vault: VAULT,
      qaRules: RULES,
      resumePdf: { filename: 'Aarav_Backend.pdf', bytes: [37, 80, 68, 70] },
    });

    // Must skip image/* photo and Cover Letter, and attach ONLY to Resume/CV!
    expect((step2Doc.getElementById('s2_photo') as HTMLInputElement).files?.length ?? 0).toBe(0);
    expect((step2Doc.getElementById('s2_cover') as HTMLInputElement).files?.length ?? 0).toBe(0);
    const resumeInput = step2Doc.getElementById('s2_resume') as HTMLInputElement;
    expect(r2.resumeAttached).toBe(true);
    expect(resumeInput.files?.[0]?.name).toBe('Aarav_Backend.pdf');
    expect((step2Doc.getElementById('s2_ctc') as HTMLInputElement).value).toBe('22');
    expect(s2NextSpy).not.toHaveBeenCalled();

    // User manually clicks Next -> Portal transitions DOM to Step 3
    // === STEP 3: Screening Questions + Submit ("ghi + jkl + submit") ===
    const step3Doc = parseHtml(`
      <div data-automation-id="jobApplication">
        <label for="s3_auth">Authorized to work in India</label>
        <select id="s3_auth">
          <option value="">Select</option>
          <option value="yes">Yes</option>
          <option value="no">No</option>
        </select>

        <label for="s3_unknown">Describe your proudest system migration</label>
        <textarea id="s3_unknown"></textarea>

        <button id="s3_submit" type="submit">Submit Application</button>
      </div>
    `);
    const s3SubmitSpy = vi.fn();
    step3Doc.getElementById('s3_submit')!.addEventListener('click', s3SubmitSpy);

    const r3 = adapter.run({
      document: step3Doc,
      pageUrl: 'https://company.wd5.myworkdayjobs.com/careers/apply/step3',
      vault: VAULT,
      qaRules: RULES,
    });

    expect((step3Doc.getElementById('s3_auth') as HTMLSelectElement).value).toBe('yes');
    expect(step3Doc.getElementById('s3_unknown')!.getAttribute('data-jobautomation-amber')).toBe('true');
    expect(r3.unknownFields).toEqual([
      { question: 'Describe your proudest system migration', fieldTag: 'textarea' },
    ]);
    expect(s3SubmitSpy).not.toHaveBeenCalled();
    expect(r3.pausedBeforeSubmit).toBe(true);
  });

  it('skips avatar/selfie/id-proof/signature file inputs when looking for resume upload', () => {
    const doc = parseHtml(`
      <form>
        <label for="f_avatar">Profile Avatar</label>
        <input id="f_avatar" type="file" />
        <label for="f_id">ID Proof</label>
        <input id="f_id" type="file" />
        <label for="f_sig">Digital Signature</label>
        <input id="f_sig" type="file" />
      </form>
    `);

    const report = getAdapterForPortal('generic').run({
      document: doc,
      pageUrl: 'https://careers.example.in/apply',
      vault: VAULT,
      qaRules: [],
      resumePdf: { filename: 'Aarav.pdf', bytes: [37, 80, 68, 70] },
    });

    expect(report.resumeAttached).toBe(false);
    expect((doc.getElementById('f_avatar') as HTMLInputElement).files?.length ?? 0).toBe(0);
    expect((doc.getElementById('f_id') as HTMLInputElement).files?.length ?? 0).toBe(0);
    expect((doc.getElementById('f_sig') as HTMLInputElement).files?.length ?? 0).toBe(0);
  });
});
