import { describe, expect, it, vi } from 'vitest';
import { detectPortalFromUrl, extractCurrentPageContext, harvestVisibleJobs } from '../content/harvester';
import { isBlockedPiiField } from '../content/pii_guard';
import { attachSubmitWatcher } from '../content/submit_watcher';
import { detectAtsFromUrl } from '../shared/ats_detector';

function parseHtml(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

describe('Extension Core Modules (PII Guard, ATS Detector, Harvester, Submit Watcher)', () => {
  it('client-side PII guard blocks all Indian Gov IDs, banking, and DoB while allowing tech questions', () => {
    for (const label of [
      'PAN Card Number',
      'PAN',
      'Aadhaar Card UIDAI',
      'Aadhar Number',
      'Passport Number',
      'Date of Birth',
      'D.O.B.',
      'Bank Account Number',
      'IFSC Code',
      'UAN Number',
      'EPFO Account',
      'SSN',
      'Driving Licence',
      'Voter ID',
    ]) {
      expect(isBlockedPiiField(label), `Should block: ${label}`).toBe(true);
    }

    for (const safe of ['', '   ', 'Expected CTC LPA', 'Notice Period Days', 'Company Name', 'Panel Interview Availability']) {
      expect(isBlockedPiiField(safe), `Should allow: ${safe}`).toBe(false);
    }
  });

  it('ATS detector handles Greenhouse embed query (?for=), malformed URLs, and Workday without locale prefix', () => {
    expect(detectAtsFromUrl('not-a-valid-url')).toBeNull();

    expect(detectAtsFromUrl('https://boards.greenhouse.io/embed/job_board?for=phonepe')).toEqual({
      slug: 'phonepe',
      display_name: 'Phonepe',
      ats_type: 'greenhouse',
      ats_config_json: { board_token: 'phonepe' },
    });

    expect(detectAtsFromUrl('https://flipkart.wd3.myworkdayjobs.com/FlipkartCareers/job/SDE2')).toEqual({
      slug: 'flipkart',
      display_name: 'Flipkart',
      ats_type: 'workday',
      ats_config_json: { tenant: 'flipkart', site: 'FlipkartCareers', instance: 'wd3' },
    });
  });

  it('Harvester detects all portal hostnames, harvests Glassdoor cards, deduplicates URLs, and extracts current page context', () => {
    expect(detectPortalFromUrl('https://www.glassdoor.co.in/Job/india-jobs.htm')).toBe('glassdoor');
    expect(detectPortalFromUrl('https://in.indeed.com/jobs?q=python')).toBe('indeed');
    expect(detectPortalFromUrl('https://random-company.com/careers')).toBe('extension');

    // Glassdoor search cards + duplicate URL dedup
    const gdDoc = parseHtml(`
      <ul>
        <li data-test="jobListing">
          <a data-test="job-title" href="/job-listing/sde-2-cred-101">SDE 2 Backend</a>
          <div data-test="employer-name">CRED</div>
          <div data-test="emp-location">Bengaluru</div>
          <div data-test="desc-snippet">Python, FastAPI, Kafka microservices.</div>
        </li>
        <li data-test="jobListing">
          <a data-test="job-title" href="/job-listing/sde-2-cred-101">SDE 2 Backend Duplicate</a>
          <div data-test="employer-name">CRED</div>
        </li>
      </ul>
    `);
    const harvested = harvestVisibleJobs(gdDoc, 'https://www.glassdoor.co.in/Job/bengaluru-jobs.htm');
    expect(harvested).toHaveLength(1);
    expect(harvested[0]).toMatchObject({
      title: 'SDE 2 Backend',
      company_name: 'CRED',
      location_raw: 'Bengaluru',
      portal_name: 'glassdoor',
    });

    // Detail page context extraction
    const detailDoc = parseHtml(`
      <html>
        <head><title>Fallback Title</title></head>
        <body>
          <h1 class="app-title">Senior Platform Engineer</h1>
          <span class="company-name">Razorpay</span>
          <span class="location">Bengaluru, India</span>
          <div id="content">Build payment switches with Go and Kafka.</div>
        </body>
      </html>
    `);
    const ctx = extractCurrentPageContext(detailDoc, 'https://boards.greenhouse.io/razorpay/jobs/9901');
    expect(ctx).toMatchObject({
      title: 'Senior Platform Engineer',
      company_name: 'Razorpay',
      location_raw: 'Bengaluru, India',
      portal_name: 'greenhouse',
      external_job_id: '9901',
    });
    expect(ctx.description_raw).toContain('Go and Kafka');
  });

  it('attachSubmitWatcher emits SUBMIT_CLICKED, MutationObserver CONFIRMATION_SEEN, and detaches cleanly', async () => {
    const doc = parseHtml(`
      <main>
        <form>
          <button id="sub_btn" type="submit">Submit Application</button>
        </form>
      </main>
    `);

    const events: string[] = [];
    const onEvent = vi.fn((ev: { type: string }) => {
      events.push(ev.type);
    });

    const detach = attachSubmitWatcher(doc, onEvent);

    // Click submit -> SUBMIT_CLICKED (only emitted once even if clicked twice)
    (doc.getElementById('sub_btn') as HTMLButtonElement).click();
    (doc.getElementById('sub_btn') as HTMLButtonElement).click();
    expect(events).toEqual(['SUBMIT_CLICKED']);

    // Portal renders thank-you screen dynamically -> MutationObserver triggers CONFIRMATION_SEEN
    const banner = doc.createElement('h1');
    banner.textContent = 'Thank you for applying! Your application has been received.';
    doc.querySelector('main')!.appendChild(banner);

    await vi.waitFor(() => {
      expect(events).toContain('CONFIRMATION_SEEN');
    });

    detach();
  });
});

