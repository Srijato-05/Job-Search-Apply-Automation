export interface DetectedAtsCompany {
  slug: string;
  display_name: string;
  ats_type: 'greenhouse' | 'lever' | 'ashby' | 'smartrecruiters' | 'workday';
  ats_config_json: Record<string, string>;
}

function toDisplayName(token: string): string {
  return token
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim();
}

/**
 * Inspect a career page URL and extract its ATS provider + board token/tenant config
 * for 1-click "+ Watch Company ATS" registration.
 */
export function detectAtsFromUrl(rawUrl: string): DetectedAtsCompany | null {
  let url: URL;
  try {
    url = new URL(rawUrl);
  } catch {
    return null;
  }

  const host = url.hostname.toLowerCase();
  const segments = url.pathname
    .split('/')
    .map((s) => s.trim())
    .filter(Boolean);

  // Greenhouse: https://boards.greenhouse.io/<token>... or job-boards.greenhouse.io/<token>
  if (host === 'boards.greenhouse.io' || host === 'job-boards.greenhouse.io') {
    const forParam = url.searchParams.get('for');
    const token = forParam || (segments[0] && segments[0] !== 'embed' ? segments[0] : '');
    if (!token) return null;
    const slug = token.toLowerCase();
    return {
      slug,
      display_name: toDisplayName(token),
      ats_type: 'greenhouse',
      ats_config_json: { board_token: token },
    };
  }

  // Lever: https://jobs.lever.co/<company>/...
  if (host === 'jobs.lever.co' && segments[0]) {
    const token = segments[0];
    return {
      slug: token.toLowerCase(),
      display_name: toDisplayName(token),
      ats_type: 'lever',
      ats_config_json: { company_name: token },
    };
  }

  // Ashby: https://jobs.ashbyhq.com/<company>/...
  if (host === 'jobs.ashbyhq.com' && segments[0]) {
    const token = segments[0];
    return {
      slug: token.toLowerCase(),
      display_name: toDisplayName(token),
      ats_type: 'ashby',
      ats_config_json: { company_name: token },
    };
  }

  // SmartRecruiters: https://jobs.smartrecruiters.com/<CompanyId>/...
  if (host === 'jobs.smartrecruiters.com' && segments[0]) {
    const companyId = segments[0];
    return {
      slug: companyId.toLowerCase(),
      display_name: toDisplayName(companyId),
      ats_type: 'smartrecruiters',
      ats_config_json: { company_id: companyId },
    };
  }

  // Workday: https://<tenant>.<wdN>.myworkdayjobs.com/<locale?>/<site>/...
  const wdMatch = host.match(/^([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com$/i);
  if (wdMatch) {
    const tenant = wdMatch[1];
    const instance = wdMatch[2];
    let siteIdx = 0;
    if (segments[0] && /^[a-z]{2}(?:-[A-Z]{2})?$/i.test(segments[0])) {
      siteIdx = 1;
    }
    const site = segments[siteIdx] || 'careers';
    return {
      slug: tenant.toLowerCase(),
      display_name: toDisplayName(tenant),
      ats_type: 'workday',
      ats_config_json: { tenant, site, instance },
    };
  }

  return null;
}

