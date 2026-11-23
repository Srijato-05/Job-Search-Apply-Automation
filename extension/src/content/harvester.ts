export interface HarvestedJob {
  title: string;
  company_name: string;
  description_raw: string;
  location_raw: string;
  portal_name: string;
  external_job_id: string | null;
  job_url: string;
  apply_url: string;
}

export interface PageContextPayload {
  page_url: string;
  apply_url: string;
  title: string;
  company_name: string;
  description_raw: string;
  location_raw: string;
  portal_name: string;
  external_job_id: string | null;
}

function cleanText(el: Element | null | undefined): string {
  return (el?.textContent ?? '').replace(/\s+/g, ' ').trim();
}

function resolveHref(anchor: Element | null | undefined, baseUrl: string): string {
  const href = anchor?.getAttribute('href') ?? '';
  if (!href) return baseUrl;
  try {
    return new URL(href, baseUrl).toString();
  } catch {
    return baseUrl;
  }
}

export function detectPortalFromUrl(rawUrl: string): string {
  const u = rawUrl.toLowerCase();
  if (u.includes('naukri.com')) return 'naukri';
  if (u.includes('linkedin.com')) return 'linkedin';
  if (u.includes('indeed.')) return 'indeed';
  if (u.includes('glassdoor.')) return 'glassdoor';
  if (u.includes('instahyre.com')) return 'instahyre';
  if (u.includes('hirist.')) return 'hirist';
  if (u.includes('cutshort.io')) return 'cutshort';
  if (u.includes('foundit.in')) return 'foundit';
  if (u.includes('careerbuilder.')) return 'careerbuilder';
  if (u.includes('greenhouse.io')) return 'greenhouse';
  if (u.includes('lever.co')) return 'lever';
  if (u.includes('ashbyhq.com')) return 'ashby';
  if (u.includes('smartrecruiters.com')) return 'smartrecruiters';
  if (u.includes('myworkdayjobs.com')) return 'workday';
  return 'extension';
}

function extractExternalId(url: string): string | null {
  const m =
    url.match(/\/(?:jobs?|view|opportunity|job-detail)\/([A-Za-z0-9_-]{3,})/i) ||
    url.match(/[?&](?:jobId|jk|currentJobId)=([A-Za-z0-9_-]+)/i);
  return m ? m[1] : null;
}

interface PortalSelectors {
  card: string;
  title: string;
  company: string;
  location: string;
  description: string;
  link: string;
}

const PORTAL_SELECTORS: Record<string, PortalSelectors> = {
  naukri: {
    card: '.srp-jobtuple-wrapper, .cust-job-tuple, article.jobTuple',
    title: 'a.title, .title a, h2 a, .title',
    company: 'a.comp-name, .comp-name, .companyInfo a',
    location: '.locWdth, .location, .loc-wrap span',
    description: '.job-desc, .ellipsis.job-description',
    link: 'a.title, .title a, h2 a',
  },
  linkedin: {
    card: '.jobs-search-results__list-item, .job-card-container, li[data-occludable-job-id]',
    title: 'a.job-card-list__title, a.job-card-container__link, .job-card-list__title',
    company: '.job-card-container__primary-description, .artdeco-entity-lockup__subtitle',
    location: '.job-card-container__metadata-item, .artdeco-entity-lockup__caption',
    description: '.job-card-list__insight, .job-card-container__footer-wrapper',
    link: 'a.job-card-list__title, a.job-card-container__link',
  },
  instahyre: {
    card: '.employer-block, .opportunity-card, [data-opportunity-id]',
    title: '.opportunity-title, .job-title, h3, h2',
    company: '.company-name, .employer-name',
    location: '.opportunity-location, .location',
    description: '.job-description, .skills, .opportunity-skills',
    link: 'a.opportunity-link, a[href*="opportunity"], h3 a, a',
  },
  hirist: {
    card: '.job-tuple, .job-card, [data-job-id]',
    title: 'a.job-title, .job-title, h2 a, h3 a',
    company: '.company-name, .recruiter-name',
    location: '.location, .loc',
    description: '.job-desc, .skills',
    link: 'a.job-title, h2 a, h3 a, a',
  },
  cutshort: {
    card: '.job-card, [data-testid="job-card"]',
    title: 'h2, h3, .job-title, a[href*="/job/"]',
    company: '.company-name, [data-testid="company-name"]',
    location: '.location, [data-testid="job-location"]',
    description: '.job-summary, .skills',
    link: 'a[href*="/job/"], h2 a, a',
  },
  foundit: {
    card: '.card-panel, .srpResultCard, .jobTuple',
    title: '.jobTitle a, .jobTitle, h3 a',
    company: '.companyName a, .companyName',
    location: '.details .loc, .location',
    description: '.job-descrip, .descrip',
    link: '.jobTitle a, h3 a, a',
  },
  careerbuilder: {
    card: '.data-results-content-parent, .job-listing-item',
    title: '.data-results-title, h2 a',
    company: '.data-details span:first-child, .company-name',
    location: '.data-details span:nth-child(2), .location',
    description: '.job-description, .block',
    link: 'a.data-results-content, h2 a, a',
  },
  glassdoor: {
    card: 'li[data-test="jobListing"], .JobsList_jobListItem__wjTHv, .react-job-listing',
    title: '[data-test="job-title"], a.JobCard_jobTitle__GLyJ1, a[data-test="job-link"]',
    company: '[data-test="employer-name"], .EmployerProfile_compactEmployerName__LE242',
    location: '[data-test="emp-location"], .JobCard_location__rCz3x',
    description: '[data-test="desc-snippet"], .JobCard_jobDescriptionSnippet__yWW8q',
    link: '[data-test="job-title"], a[data-test="job-link"], a',
  },
};

/**
 * Extract visible job cards on the active portal tab when the user clicks "Capture Visible Jobs".
 */
export function harvestVisibleJobs(doc: Document, pageUrl: string): HarvestedJob[] {
  const portal = detectPortalFromUrl(pageUrl);
  const sel = PORTAL_SELECTORS[portal];
  if (!sel) return [];

  const cards = Array.from(doc.querySelectorAll(sel.card));
  const seenUrls = new Set<string>();
  const results: HarvestedJob[] = [];

  for (const card of cards) {
    const titleEl = card.querySelector(sel.title);
    const title = cleanText(titleEl);
    const company = cleanText(card.querySelector(sel.company));
    if (!title || !company) continue;

    const linkEl = card.querySelector(sel.link) ?? titleEl;
    const jobUrl = resolveHref(linkEl, pageUrl);
    if (seenUrls.has(jobUrl)) continue;
    seenUrls.add(jobUrl);

    const location = cleanText(card.querySelector(sel.location));
    const desc = cleanText(card.querySelector(sel.description)) || cleanText(card);
    const attrId =
      card.getAttribute('data-job-id') ||
      card.getAttribute('data-occludable-job-id') ||
      card.getAttribute('data-opportunity-id');

    results.push({
      title,
      company_name: company,
      description_raw: desc,
      location_raw: location,
      portal_name: portal,
      external_job_id: attrId || extractExternalId(jobUrl),
      job_url: jobUrl,
      apply_url: jobUrl,
    });
  }

  return results;
}

/**
 * Extract the active job posting context for /api/v1/extension/check-page.
 */
export function extractCurrentPageContext(doc: Document, pageUrl: string): PageContextPayload {
  const portal = detectPortalFromUrl(pageUrl);

  const title =
    cleanText(
      doc.querySelector(
        '.job-details-jobs-unified-top-card__job-title, .jd-header-title, h1.app-title, .posting-headline h2, h1',
      ),
    ) || doc.title;

  const company = cleanText(
    doc.querySelector(
      '.job-details-jobs-unified-top-card__company-name, .jd-header-comp-name a, .company-name, .posting-headline .company, [data-company-name]',
    ),
  );

  const location = cleanText(
    doc.querySelector(
      '.job-details-jobs-unified-top-card__bullet, .location, .loc, .posting-categories .location',
    ),
  );

  const description =
    cleanText(
      doc.querySelector(
        '.jobs-description__content, .job-desc, .dang-inner-html, #content, .posting-description, main',
      ),
    ) || cleanText(doc.body);

  return {
    page_url: pageUrl,
    apply_url: pageUrl,
    title: title.slice(0, 200),
    company_name: company.slice(0, 120),
    description_raw: description.slice(0, 12000),
    location_raw: location.slice(0, 120),
    portal_name: portal,
    external_job_id: extractExternalId(pageUrl),
  };
}

