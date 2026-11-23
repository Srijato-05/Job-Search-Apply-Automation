import { describe, expect, it, vi } from 'vitest';
import { ALL_ADAPTER_NAMES, getAdapterForPortal } from '../content/adapters';
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
    normalized_question: 'are you comfortable with relocation',
    canonical_aliases_json: ['open to relocate'],
    verified_answer: 'Yes',
  },
];

interface PortalFixtureCase {
  portal: string;
  url: string;
  html: string;
  expectedFilledSelector: string;
  expectedFilledValue: string;
  expectResumeAttached?: boolean;
}

const ADAPTER_FIXTURES: PortalFixtureCase[] = [
  {
    portal: 'greenhouse',
    url: 'https://boards.greenhouse.io/razorpay/jobs/1',
    html: `<form id="application_form"><label for="g_name">Full Name</label><input id="g_name" type="text"/><input id="g_res" type="file" aria-label="Resume"/></form>`,
    expectedFilledSelector: '#g_name',
    expectedFilledValue: 'Aarav Sharma',
    expectResumeAttached: true,
  },
  {
    portal: 'lever',
    url: 'https://jobs.lever.co/atlassian/abc',
    html: `<div class="application-form"><label for="l_mail">Email</label><input id="l_mail" type="email"/><input name="resume" type="file"/></div>`,
    expectedFilledSelector: '#l_mail',
    expectedFilledValue: 'aarav@example.com',
    expectResumeAttached: true,
  },
  {
    portal: 'ashby',
    url: 'https://jobs.ashbyhq.com/rippling/role',
    html: `<form class="ashby-job-posting-form"><label for="a_gh">GitHub URL</label><input id="a_gh" type="url"/><input type="file" aria-label="Resume"/></form>`,
    expectedFilledSelector: '#a_gh',
    expectedFilledValue: 'https://github.com/aarav',
    expectResumeAttached: true,
  },
  {
    portal: 'smartrecruiters',
    url: 'https://jobs.smartrecruiters.com/BoschGroup/1',
    html: `<oc-apply-form><label for="sr_city">Current City</label><input id="sr_city" type="text"/></oc-apply-form>`,
    expectedFilledSelector: '#sr_city',
    expectedFilledValue: 'Bengaluru',
  },
  {
    portal: 'workday',
    url: 'https://walmart.wd5.myworkdayjobs.com/External/job/1',
    html: `<div data-automation-id="jobApplication"><label for="wd_exp">Total Experience</label><input id="wd_exp" type="number"/></div>`,
    expectedFilledSelector: '#wd_exp',
    expectedFilledValue: '4.5',
  },
  {
    portal: 'naukri',
    url: 'https://www.naukri.com/job-listings-1',
    html: `<form id="applyForm"><label for="nk_ctc">Expected CTC</label><input id="nk_ctc" type="text"/></form>`,
    expectedFilledSelector: '#nk_ctc',
    expectedFilledValue: '32',
  },
  {
    portal: 'linkedin',
    url: 'https://www.linkedin.com/jobs/view/1',
    html: `<div class="jobs-easy-apply-modal"><label for="li_ph">Mobile phone number</label><input id="li_ph" type="tel"/></div>`,
    expectedFilledSelector: '#li_ph',
    expectedFilledValue: '+91-9876543210',
  },
  {
    portal: 'indeed',
    url: 'https://in.indeed.com/viewjob?jk=abc',
    html: `<div id="ia-container"><label for="in_10">10th Percentage</label><input id="in_10" type="text"/></div>`,
    expectedFilledSelector: '#in_10',
    expectedFilledValue: '94.2',
  },
  {
    portal: 'instahyre',
    url: 'https://www.instahyre.com/opportunity/1',
    html: `<div id="candidate-apply-form"><label for="ih_np">Notice Period</label><input id="ih_np" type="number"/></div>`,
    expectedFilledSelector: '#ih_np',
    expectedFilledValue: '30',
  },
  {
    portal: 'foundit',
    url: 'https://www.foundit.in/job/1',
    html: `<div class="apply-drawer"><label for="fd_li">LinkedIn URL</label><input id="fd_li" type="url"/></div>`,
    expectedFilledSelector: '#fd_li',
    expectedFilledValue: 'https://linkedin.com/in/aarav',
  },
  {
    portal: 'hirist',
    url: 'https://www.hirist.tech/j/1',
    html: `<div class="apply-form"><label for="hr_ctc">Current CTC</label><input id="hr_ctc" type="text"/></div>`,
    expectedFilledSelector: '#hr_ctc',
    expectedFilledValue: '22',
  },
  {
    portal: 'cutshort',
    url: 'https://cutshort.io/job/1',
    html: `<div class="apply-modal"><label for="cs_web">Portfolio</label><input id="cs_web" type="url"/></div>`,
    expectedFilledSelector: '#cs_web',
    expectedFilledValue: 'https://aarav.dev',
  },
  {
    portal: 'glassdoor', // falls back cleanly to generic_heuristic
    url: 'https://www.glassdoor.co.in/job-listing/1',
    html: `<form><label for="gd_mail">Email</label><input id="gd_mail" type="email"/><button type="submit">Submit Application</button></form>`,
    expectedFilledSelector: '#gd_mail',
    expectedFilledValue: 'aarav@example.com',
  },
];

describe('All 13 Portal Adapters + Glassdoor Fallback', () => {
  it('resolves every registered adapter plus generic fallback for unmapped portals', () => {
    expect(ALL_ADAPTER_NAMES).toHaveLength(13);
    expect(getAdapterForPortal('glassdoor').name).toBe('generic_heuristic');
    expect(getAdapterForPortal('unknown-portal').name).toBe('generic_heuristic');
  });

  it.each(ADAPTER_FIXTURES)(
    'autofills $portal ($url) accurately and pauses before submit',
    ({ portal, url, html, expectedFilledSelector, expectedFilledValue, expectResumeAttached }) => {
      const doc = parseHtml(`${html}<button id="sub_btn" type="submit">Submit</button>`);
      const submitSpy = vi.fn();
      doc.getElementById('sub_btn')!.addEventListener('click', submitSpy);

      const report = getAdapterForPortal(portal).run({
        document: doc,
        pageUrl: url,
        vault: VAULT,
        qaRules: RULES,
        resumePdf: { filename: 'Aarav.pdf', bytes: [37, 80, 68, 70] },
      });

      expect((doc.querySelector(expectedFilledSelector) as HTMLInputElement).value).toBe(
        expectedFilledValue,
      );
      if (expectResumeAttached) {
        expect(report.resumeAttached).toBe(true);
      }
      expect(report.pausedBeforeSubmit).toBe(true);
      expect(submitSpy).not.toHaveBeenCalled();
    },
  );

  it('blocks PII questions even inside Naukri Chatbot drawer', () => {
    const doc = parseHtml(`
      <div class="chatbot_Drawer">
        <div class="botMsg"><span>Please provide your PAN Card number</span></div>
        <div class="chatbot_InputContainer"><input class="chatbot_Input" type="text" /></div>
      </div>
    `);
    const report = getAdapterForPortal('naukri').run({
      document: doc,
      pageUrl: 'https://www.naukri.com/job-listings-99',
      vault: VAULT,
      qaRules: RULES,
    });
    expect((doc.querySelector('.chatbot_Input') as HTMLInputElement).value).toBe('');
    expect(report.blockedPiiFields).toContain('Please provide your PAN Card number');
  });
});

