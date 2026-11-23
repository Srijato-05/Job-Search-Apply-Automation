import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobDetailDrawer } from '../components/JobDetailDrawer';
import { CollectorsPage } from '../pages/CollectorsPage';
import { JobQueuePage } from '../pages/JobQueuePage';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response);
}

describe('Frontend Multi-Filter, Track Switching, Sibling Switch & Watchlist Interactions', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = 'test-token';
    vi.restoreAllMocks();
  });

  it('JobQueuePage toggles multi-tier selection (S+A -> deselect S) and renders Sibling/Repost/LPA badges', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes')) return jsonResponse([]);
      return jsonResponse({
        total: 1,
        items: [
          {
            id: 201,
            title: 'Staff Backend Engineer',
            company_name: 'CRED',
            company_slug: 'cred',
            role_subtag: 'Payments • Go',
            req_id: 'JR500',
            normalized_city: 'Bengaluru',
            office_locality: 'Indiranagar',
            work_mode: 'hybrid',
            exp_min_years: 4,
            exp_max_years: 7,
            salary_min_lpa: 30,
            salary_max_lpa: 45,
            max_notice_days: 30,
            notice_compatible: true,
            apply_friction: 'fast_apply',
            employer_type: 'direct_product',
            hidden_by_gate1: false,
            hidden_reason: null,
            status: 'active',
            parent_sibling_job_id: 200,
            repost_count: 3,
            posted_at: null,
            first_seen_at: '2026-11-23T00:00:00Z',
            last_reposted_at: '2026-11-23T00:00:00Z',
            winning_score: null,
            sources: [],
          },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<JobQueuePage />);

    expect(await screen.findByText('Sibling Role')).toBeInTheDocument();
    expect(screen.getByText('3 mirror/repost(s)')).toBeInTheDocument();
    expect(screen.getByText(/₹30–45 LPA/)).toBeInTheDocument();

    // Select Tier S and Tier A -> tier=S,A, then deselect Tier S -> tier=A
    await user.click(screen.getByRole('button', { name: 'Tier S' }));
    await user.click(screen.getByRole('button', { name: 'Tier A' }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => decodeURIComponent(String(c[0])).includes('tier=S,A'))).toBe(true);
    });

    await user.click(screen.getByRole('button', { name: 'Tier S' }));
    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => decodeURIComponent(String(c[0])));
      expect(urls.some((u) => u.endsWith('tier=A'))).toBe(true);
    });
  });

  it('JobDetailDrawer switches between multiple resume tracks and multiple sibling diffs', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/applications/cooldown/cred')) {
        return jsonResponse({ company_slug: 'cred', apps_last_30d: 0, max_company_apps_30d: 3, remaining_apps: 3, is_at_limit: false, next_slot_opens_at: null, warning_message: null });
      }
      if (url.includes('/api/v1/jobs/201/diff/202')) {
        return jsonResponse({
          job_a_id: 201,
          job_b_id: 202,
          job_a_subtag: 'Payments • Go',
          job_b_subtag: 'Frontend • React',
          similarity_pct: 25,
          shared_skills: [],
          only_in_job_a_skills: ['Go'],
          only_in_job_b_skills: ['React'],
          unchanged_lines: [],
          removed_lines: ['Go gRPC'],
          added_lines: ['React UI 202'],
        });
      }
      if (url.includes('/api/v1/jobs/201/diff/203')) {
        return jsonResponse({
          job_a_id: 201,
          job_b_id: 203,
          job_a_subtag: 'Payments • Go',
          job_b_subtag: 'Data • Spark',
          similarity_pct: 30,
          shared_skills: [],
          only_in_job_a_skills: ['Go'],
          only_in_job_b_skills: ['Spark'],
          unchanged_lines: [],
          removed_lines: ['Go gRPC'],
          added_lines: ['Spark ETL 203'],
        });
      }
      return jsonResponse({
        id: 201,
        title: 'SDE II',
        company_name: 'CRED',
        company_slug: 'cred',
        role_subtag: 'Payments • Go',
        req_id: 'JR500',
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
        first_seen_at: '2026-11-23T00:00:00Z',
        last_reposted_at: '2026-11-23T00:00:00Z',
        winning_score: null,
        sources: [],
        description_raw: 'Raw JD',
        boilerplate_stripped_text: 'Clean JD',
        primary_skills_json: ['Go'],
        secondary_skills_json: [],
        portal_signals_json: {},
        all_scores: [
          {
            resume_id: 1,
            track_name: 'Track Go',
            pdf_filename: 'go.pdf',
            tier: 'S',
            is_winning_resume: true,
            semantic_bullet_coverage_pct: 90,
            matched_primary_skills_json: ['Go'],
            missing_primary_skills_json: [],
            missing_secondary_skills_json: [],
            bullet_proof_json: [{ jd_requirement: 'Build Go services', matched_bullet: 'PROOF_GO_BULLET', section_name: 'exp', similarity: 0.92, status: 'MATCHED' }],
            cross_resume_alerts_json: [],
            scored_at: '2026-11-23T00:00:00Z',
          },
          {
            resume_id: 2,
            track_name: 'Track React',
            pdf_filename: 'react.pdf',
            tier: 'C',
            is_winning_resume: false,
            semantic_bullet_coverage_pct: 20,
            matched_primary_skills_json: [],
            missing_primary_skills_json: ['Go'],
            missing_secondary_skills_json: [],
            bullet_proof_json: [{ jd_requirement: 'Build Go services', matched_bullet: null, section_name: null, similarity: 0.1, status: 'GAP' }],
            cross_resume_alerts_json: [],
            scored_at: '2026-11-23T00:00:00Z',
          },
        ],
        sibling_jobs: [
          { id: 202, title: 'SDE II', role_subtag: 'Frontend • React', req_id: 'JR501', normalized_city: 'Bengaluru', status: 'active' },
          { id: 203, title: 'SDE II', role_subtag: 'Data • Spark', req_id: 'JR502', normalized_city: 'Bengaluru', status: 'active' },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<JobDetailDrawer jobId={201} onClose={() => {}} />);

    expect(await screen.findByText('PROOF_GO_BULLET')).toBeInTheDocument();

    // Switch to Track React -> displays GAP row instead of PROOF_GO_BULLET
    await user.click(screen.getByRole('button', { name: /Track React — Tier C/i }));
    expect(screen.queryByText('PROOF_GO_BULLET')).not.toBeInTheDocument();
    expect(screen.getByText('No direct bullet match')).toBeInTheDocument();

    // Switch to Sibling Diff tab & select second sibling #203
    await user.click(screen.getByRole('button', { name: /Sibling JD Diff/i }));
    expect(await screen.findByText(/\+ React UI 202/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /#203 Data • Spark/i }));
    expect(await screen.findByText(/\+ Spark ETL 203/)).toBeInTheDocument();
  });

  it('CollectorsPage filters watchlist by search, toggles Watching status, and shows live progress banner', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/collectors/scheduler')) return jsonResponse({ running: false, interval_hours: 4 });
      if (url.includes('/api/v1/collectors/health')) {
        return jsonResponse({ total_sources: 2, healthy_sources: 2, cooldown_sources: 0, error_sources: 0, sources: [] });
      }
      if (url.includes('/api/v1/collectors/progress')) {
        return jsonResponse({ running: true, target: 'ats', phase: 'ats', completed: 12, total: 68, current_item: 'Razorpay', fetched_so_far: 40, new_so_far: 9 });
      }
      if (url.includes('/api/v1/watchlist/swiggy') && init?.method === 'PATCH') {
        return jsonResponse({ slug: 'swiggy', is_watched: false });
      }
      if (url.includes('/api/v1/watchlist')) {
        return jsonResponse([
          { slug: 'razorpay', display_name: 'Razorpay', employer_type: 'direct_product', ats_type: 'greenhouse', ats_config_json: {}, is_watched: true, is_blacklisted: false, health_status: 'ok', last_polled_at: null },
          { slug: 'swiggy', display_name: 'Swiggy', employer_type: 'direct_product', ats_type: 'lever', ats_config_json: {}, is_watched: true, is_blacklisted: false, health_status: 'cooldown', last_polled_at: null },
        ]);
      }
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<CollectorsPage />);

    // Live running banner rendered
    expect(await screen.findByText(/Running ats: 12\/68 — Razorpay \(9 new\)/)).toBeInTheDocument();
    expect(screen.getByText('Swiggy')).toBeInTheDocument();

    // Filter to Swiggy -> Razorpay disappears
    await user.type(screen.getByPlaceholderText(/Filter watched companies/i), 'swiggy');
    expect(screen.queryByText('Razorpay')).not.toBeInTheDocument();
    expect(screen.getByText('Swiggy')).toBeInTheDocument();

    // Click Watching button -> PATCH /api/v1/watchlist/swiggy
    await user.click(screen.getByRole('button', { name: 'Watching' }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/v1/watchlist/swiggy') && c[1]?.method === 'PATCH')).toBe(true);
    });
  });
});

