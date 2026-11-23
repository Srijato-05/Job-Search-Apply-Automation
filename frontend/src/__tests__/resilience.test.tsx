import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobDetailDrawer } from '../components/JobDetailDrawer';
import { ApplicationsPage } from '../pages/ApplicationsPage';
import { CollectorsPage } from '../pages/CollectorsPage';
import { FactVaultPage } from '../pages/FactVaultPage';
import { JobQueuePage } from '../pages/JobQueuePage';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response);
}

describe('Frontend Network Failure, Offline & API Error Resilience', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = 'test-token';
    vi.restoreAllMocks();
  });

  it('JobQueuePage renders error banner on network outage or HTTP 500 without crashing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/v1/resumes')) return jsonResponse([]);
        return Promise.reject(new TypeError('Failed to fetch'));
      }),
    );

    const { unmount } = render(<JobQueuePage />);
    expect(await screen.findByText('Failed to fetch')).toBeInTheDocument();
    unmount();

    // Also test HTTP 500 JSON error response
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/v1/resumes')) return jsonResponse([]);
        return jsonResponse({ detail: 'Database locked during maintenance' }, 500);
      }),
    );

    render(<JobQueuePage />);
    expect(await screen.findByText('Database locked during maintenance')).toBeInTheDocument();
  });

  it('FactVaultPage surfaces initial offline load error and invalid ZIP restore 422 error', async () => {
    // 1. Complete backend offline on initial load
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('NetworkError when attempting to fetch resource')));
    const { unmount } = render(<FactVaultPage />);
    expect(await screen.findByText(/NetworkError when attempting to fetch resource/)).toBeInTheDocument();
    unmount();

    // 2. Loaded vault, then user uploads corrupt ZIP -> 422 error shown
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.includes('/api/v1/backup/restore') && init?.method === 'POST') {
          return jsonResponse({ detail: 'Uploaded file is not a valid ZIP archive.' }, 422);
        }
        if (url.includes('/api/v1/vault/qa-rules')) return jsonResponse([]);
        return jsonResponse({
          full_name: 'Aarav',
          email: 'a@example.com',
          phone: '9999999999',
          linkedin_url: '',
          github_url: '',
          portfolio_url: '',
          leetcode_url: '',
          current_ctc_lpa: 20,
          current_fixed_lpa: 18,
          current_variable_lpa: 2,
          expected_ctc_lpa: 30,
          min_acceptable_hike_pct: 30,
          notice_period_days: 30,
          serving_notice: false,
          last_working_day: null,
          notice_negotiable: true,
          min_negotiable_days: 15,
          total_exp_years: 4,
          relevant_exp_years: 4,
          skill_years_json: {},
          current_city: 'Bengaluru',
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
      }),
    );

    render(<FactVaultPage />);
    expect(await screen.findByDisplayValue('Aarav')).toBeInTheDocument();

    const restoreInput = document.querySelector('input[type="file"][accept=".zip"]') as HTMLInputElement;
    const badZip = new File(['corrupt'], 'bad.zip', { type: 'application/zip' });
    fireEvent.change(restoreInput, { target: { files: [badZip] } });

    expect(await screen.findByText('Uploaded file is not a valid ZIP archive.')).toBeInTheDocument();
  });

  it('CollectorsPage handles 409 overlap conflict banner when sweep already running', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/v1/collectors/run')) {
          return jsonResponse({ detail: 'A collection sweep is already in progress.' }, 409);
        }
        if (url.includes('/api/v1/collectors/scheduler')) return jsonResponse({ running: false, interval_hours: 4 });
        if (url.includes('/api/v1/collectors/health')) {
          return jsonResponse({ total_sources: 0, healthy_sources: 0, cooldown_sources: 0, error_sources: 0, sources: [] });
        }
        if (url.includes('/api/v1/collectors/progress')) {
          return jsonResponse({ running: false, target: null, phase: 'idle', completed: 0, total: 0, current_item: null, fetched_so_far: 0, new_so_far: 0 });
        }
        return jsonResponse([]);
      }),
    );

    const user = userEvent.setup();
    render(<CollectorsPage />);
    await user.click(await screen.findByRole('button', { name: /Run ATS Sweep/i }));
    expect(await screen.findByText('A collection sweep is already in progress.')).toBeInTheDocument();
  });

  it('ApplicationsPage survives analytics endpoint error and JobDetailDrawer survives cooldown failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/v1/applications/analytics')) {
          return jsonResponse({ detail: 'Analytics unavailable' }, 500);
        }
        if (url.includes('/api/v1/applications/cooldown/razorpay')) {
          return Promise.reject(new Error('Cooldown timeout'));
        }
        if (url.includes('/api/v1/applications')) {
          return jsonResponse([
            {
              id: 1,
              job_id: 101,
              company_slug: 'razorpay',
              resume_id: 1,
              stage: 'applied',
              autofill_started_at: null,
              submitted_at: '2026-11-23T00:00:00Z',
              detection_method: 'manual',
              portal_used: 'greenhouse',
              jd_snapshot_text: 'Snapshot',
              resume_filename_snapshot: 'be.pdf',
              submitted_answers_json: {},
              recruiter_notes: '',
              job_title: 'Backend Engineer',
              company_name: 'Razorpay',
              resume_track_name: 'Backend',
              cooldown: null,
            },
          ]);
        }
        if (url.includes('/api/v1/jobs/101')) {
          return jsonResponse({
            id: 101,
            title: 'Backend Engineer',
            company_name: 'Razorpay',
            company_slug: 'razorpay',
            role_subtag: 'Backend',
            req_id: 'JR1',
            normalized_city: 'Bengaluru',
            office_locality: '',
            work_mode: 'hybrid',
            exp_min_years: 3,
            exp_max_years: 5,
            salary_min_lpa: null,
            salary_max_lpa: null,
            max_notice_days: 30,
            notice_compatible: true,
            apply_friction: 'fast_apply',
            employer_type: 'direct_product',
            hidden_by_gate1: false,
            hidden_reason: null,
            status: 'active',
            parent_sibling_job_id: null,
            repost_count: 0,
            posted_at: null,
            first_seen_at: '2026-11-22T00:00:00Z',
            last_reposted_at: '2026-11-22T00:00:00Z',
            winning_score: null,
            sources: [],
            description_raw: 'Raw JD',
            boilerplate_stripped_text: 'Clean JD',
            primary_skills_json: ['Python'],
            secondary_skills_json: [],
            portal_signals_json: {},
            all_scores: [],
            sibling_jobs: [],
          });
        }
        return jsonResponse({});
      }),
    );

    const { unmount } = render(<ApplicationsPage />);
    expect(await screen.findByText(/Backend Engineer — Razorpay/)).toBeInTheDocument();
    unmount();

    render(<JobDetailDrawer jobId={101} onClose={() => {}} />);
    expect(await screen.findByText('Backend Engineer')).toBeInTheDocument();
  });
});

