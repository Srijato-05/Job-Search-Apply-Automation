import { describe, expect, it } from 'vitest';
import { harvestVisibleJobs } from '../content/harvester';
import {
  detectConfirmationScreen,
  detectExpiredPosting,
  detectNativeAppliedBadge,
} from '../content/submit_watcher';
import { detectAtsFromUrl } from '../shared/ats_detector';

function parseHtml(html: string): Document {
  return new DOMParser().parseFromString(html, 'text/html');
}

describe('ATS URL Detector', () => {
  it('detects Greenhouse, Lever, Ashby, SmartRecruiters, and Workday tokens', () => {
    expect(detectAtsFromUrl('https://boards.greenhouse.io/razorpay/jobs/1234')).toEqual({
      slug: 'razorpay',
      display_name: 'Razorpay',
      ats_type: 'greenhouse',
      ats_config_json: { board_token: 'razorpay' },
    });

    expect(detectAtsFromUrl('https://jobs.lever.co/atlassian/abc-123')).toEqual({
      slug: 'atlassian',
      display_name: 'Atlassian',
      ats_type: 'lever',
      ats_config_json: { company_name: 'atlassian' },
    });

    expect(detectAtsFromUrl('https://jobs.ashbyhq.com/rippling/role-99')).toEqual({
      slug: 'rippling',
      display_name: 'Rippling',
      ats_type: 'ashby',
      ats_config_json: { company_name: 'rippling' },
    });

    expect(detectAtsFromUrl('https://jobs.smartrecruiters.com/BoschGroup/743999')).toEqual({
      slug: 'boschgroup',
      display_name: 'BoschGroup',
      ats_type: 'smartrecruiters',
      ats_config_json: { company_id: 'BoschGroup' },
    });

    expect(
      detectAtsFromUrl('https://walmart.wd5.myworkdayjobs.com/en-US/WalmartExternal/job/SDE_JR8801'),
    ).toEqual({
      slug: 'walmart',
      display_name: 'Walmart',
      ats_type: 'workday',
      ats_config_json: { tenant: 'walmart', site: 'WalmartExternal', instance: 'wd5' },
    });

    expect(detectAtsFromUrl('https://www.google.com/search?q=jobs')).toBeNull();
  });
});

describe('DOM Harvester across India Job Portals', () => {
  it('harvests Naukri, LinkedIn, Instahyre, Hirist, Cutshort, and Foundit job cards accurately', () => {
    const naukriDoc = parseHtml(`
      <div class="srp-jobtuple-wrapper" data-job-id="nk-101">
        <a class="title" href="/job-listings-backend-sde-razorpay-101">Backend SDE II</a>
        <a class="comp-name">Razorpay</a>
        <span class="locWdth">Bengaluru</span>
        <div class="job-desc">Python, FastAPI, Kafka microservices.</div>
      </div>
    `);
    const naukriJobs = harvestVisibleJobs(naukriDoc, 'https://www.naukri.com/backend-jobs');
    expect(naukriJobs).toHaveLength(1);
    expect(naukriJobs[0]).toMatchObject({
      title: 'Backend SDE II',
      company_name: 'Razorpay',
      location_raw: 'Bengaluru',
      portal_name: 'naukri',
      external_job_id: 'nk-101',
    });

    const linkedinDoc = parseHtml(`
      <ul>
        <li class="jobs-search-results__list-item" data-occludable-job-id="li-777">
          <a class="job-card-container__link" href="/jobs/view/777/">Staff Backend Engineer</a>
          <span class="artdeco-entity-lockup__subtitle">CRED</span>
          <span class="job-card-container__metadata-item">Bengaluru, Karnataka (Hybrid)</span>
        </li>
      </ul>
    `);
    const liJobs = harvestVisibleJobs(linkedinDoc, 'https://www.linkedin.com/jobs/search/');
    expect(liJobs).toHaveLength(1);
    expect(liJobs[0].company_name).toBe('CRED');
    expect(liJobs[0].portal_name).toBe('linkedin');

    const instahyreDoc = parseHtml(`
      <div class="opportunity-card" data-opportunity-id="ih-55">
        <div class="opportunity-title">Platform Engineer</div>
        <div class="company-name">Postman</div>
        <div class="opportunity-location">Bengaluru</div>
        <a class="opportunity-link" href="/opportunity/55">View</a>
        <div class="job-description">Go, Kubernetes, AWS</div>
      </div>
    `);
    expect(harvestVisibleJobs(instahyreDoc, 'https://www.instahyre.com/candidate/opportunities/')[0].company_name).toBe(
      'Postman',
    );

    const hiristDoc = parseHtml(`
      <div class="job-tuple" data-job-id="hr-12">
        <a class="job-title" href="/j/12">Full Stack React/Node</a>
        <span class="company-name">Meesho</span>
        <span class="location">Bengaluru</span>
      </div>
    `);
    expect(harvestVisibleJobs(hiristDoc, 'https://www.hirist.tech/search')[0].portal_name).toBe('hirist');

    const cutshortDoc = parseHtml(`
      <div class="job-card">
        <h3>Senior Backend Engineer</h3>
        <div class="company-name">Groww</div>
        <div class="location">Bengaluru</div>
        <a href="/job/groww-backend-90">Apply</a>
      </div>
    `);
    expect(harvestVisibleJobs(cutshortDoc, 'https://cutshort.io/jobs')[0].company_name).toBe('Groww');

    const founditDoc = parseHtml(`
      <div class="card-panel">
        <div class="jobTitle"><a href="/job/fd-88">SDE II</a></div>
        <div class="companyName">Swiggy</div>
        <div class="details"><span class="loc">Hyderabad</span></div>
      </div>
    `);
    expect(harvestVisibleJobs(founditDoc, 'https://www.foundit.in/srp/results')[0].location_raw).toBe('Hyderabad');
  });
});

describe('Submit & Expired Watcher', () => {
  it('detects native Applied badges, confirmation screens, and expired postings without false positives', () => {
    const appliedDoc = parseHtml(`<button class="jobs-s-apply--applied">Applied</button>`);
    expect(detectNativeAppliedBadge(appliedDoc)).toBe(true);

    const applyNowDoc = parseHtml(`<button>Apply now</button>`);
    expect(detectNativeAppliedBadge(applyNowDoc)).toBe(false);

    const confirmDoc = parseHtml(`<main><h1>Thank you for applying!</h1><p>Your application has been submitted.</p></main>`);
    expect(detectConfirmationScreen(confirmDoc)).toBe(true);

    const expiredDoc = parseHtml(`<div role="alert">No longer accepting applications</div>`);
    expect(detectExpiredPosting(expiredDoc)).toBe(true);
  });
});

