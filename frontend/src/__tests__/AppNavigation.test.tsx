import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response);
}

function stubAllEndpoints() {
  return vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes('/api/v1/resumes')) return jsonResponse([]);
    if (url.includes('/api/v1/jobs')) return jsonResponse({ total: 0, items: [] });
    if (url.includes('/api/v1/applications/analytics')) {
      return jsonResponse({
        total_drafts: 0,
        total_submitted: 0,
        response_rate_pct: 0,
        stage_counts: {},
        track_skill_gaps: [],
      });
    }
    if (url.includes('/api/v1/applications')) return jsonResponse([]);
    if (url.includes('/api/v1/vault/qa-rules')) return jsonResponse([]);
    if (url.includes('/api/v1/vault')) {
      return jsonResponse({
        full_name: 'Aarav',
        email: '',
        phone: '',
        linkedin_url: '',
        github_url: '',
        portfolio_url: '',
        leetcode_url: '',
        current_ctc_lpa: 0,
        current_fixed_lpa: 0,
        current_variable_lpa: 0,
        expected_ctc_lpa: 0,
        min_acceptable_hike_pct: 30,
        notice_period_days: 0,
        serving_notice: false,
        last_working_day: null,
        notice_negotiable: false,
        min_negotiable_days: null,
        total_exp_years: 0,
        relevant_exp_years: 0,
        skill_years_json: {},
        current_city: '',
        hometown: '',
        preferred_cities_json: [],
        willing_to_relocate: true,
        work_modes_json: [],
        open_to_rotational_shifts: false,
        tenth_pct: null,
        tenth_board: '',
        tenth_year: null,
        twelfth_pct: null,
        twelfth_board: '',
        twelfth_year: null,
        education_history_json: [],
        active_backlogs: 0,
        work_history_json: [],
        negative_keywords_json: [],
        company_blacklist_json: [],
        max_company_apps_30d: 3,
      });
    }
    if (url.includes('/api/v1/collectors/scheduler')) return jsonResponse({ running: false, interval_hours: 4 });
    if (url.includes('/api/v1/collectors/health')) {
      return jsonResponse({ total_sources: 0, healthy_sources: 0, cooldown_sources: 0, error_sources: 0, sources: [] });
    }
    if (url.includes('/api/v1/collectors/progress')) {
      return jsonResponse({ running: false, target: null, phase: 'idle', completed: 0, total: 0, current_item: null, fetched_so_far: 0, new_so_far: 0 });
    }
    if (url.includes('/api/v1/watchlist')) return jsonResponse([]);
    return jsonResponse({});
  });
}

describe('Full App Navigation & Dev Loopback Token Prompt', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = undefined;
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it('shows Dev Mode token prompt when token is missing, persists token on submit, and navigates all 5 sidebar routes', async () => {
    vi.stubGlobal('fetch', stubAllEndpoints());
    const user = userEvent.setup();
    render(<App />);

    // Missing token banner is visible
    expect(screen.getByText('Missing Token')).toBeInTheDocument();
    const tokenInput = screen.getByPlaceholderText('X-Local-Token');
    await user.type(tokenInput, 'my-dev-token-999');
    await user.click(screen.getByRole('button', { name: 'Save Token' }));

    await waitFor(() => {
      expect(screen.getByText('Active Token')).toBeInTheDocument();
    });
    expect(window.localStorage.getItem('job_automation_local_token')).toBe('my-dev-token-999');

    // Navigate through all 5 pages cleanly
    await user.click(screen.getByRole('button', { name: /Applications CRM/i }));
    expect(await screen.findByText('Applications Mini-CRM')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Resume Tracks/i }));
    expect(await screen.findByText('Multi-Resume Tracks')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Collectors & Watchlist/i }));
    expect(await screen.findByRole('heading', { name: 'Collectors & Watchlist' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Fact Vault & Backup/i }));
    expect(await screen.findByRole('heading', { name: /India Fact Vault/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Job Queue/i }));
    expect(await screen.findByRole('heading', { name: 'Job Queue' })).toBeInTheDocument();
  });
});

