import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApplicationsPage } from '../pages/ApplicationsPage';
import { CollectorsPage } from '../pages/CollectorsPage';
import { FactVaultPage } from '../pages/FactVaultPage';
import { JobQueuePage } from '../pages/JobQueuePage';
import { ResumesPage } from '../pages/ResumesPage';

function jsonResponse(data: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response);
}

const SAMPLE_JOB_CARD = {
  id: 101,
  title: 'SDE II Payments',
  company_name: 'Razorpay',
  company_slug: 'razorpay',
  role_subtag: 'Payments • Python',
  req_id: 'JR9001',
  normalized_city: 'Bengaluru',
  office_locality: 'Koramangala',
  work_mode: 'hybrid',
  exp_min_years: 3,
  exp_max_years: 5,
  salary_min_lpa: 28,
  salary_max_lpa: 40,
  max_notice_days: 30,
  notice_compatible: true,
  apply_friction: 'fast_apply',
  employer_type: 'direct_product',
  hidden_by_gate1: false,
  hidden_reason: null,
  status: 'active',
  parent_sibling_job_id: null,
  repost_count: 2,
  posted_at: null,
  first_seen_at: '2026-11-22T00:00:00Z',
  last_reposted_at: '2026-11-22T00:00:00Z',
  winning_score: {
    resume_id: 1,
    track_name: 'Backend Python',
    pdf_filename: 'be.pdf',
    tier: 'A',
    semantic_bullet_coverage_pct: 78.0,
    matched_primary_skills_json: ['Python'],
    missing_primary_skills_json: ['Go'],
    missing_secondary_skills_json: [],
    cross_resume_alerts_count: 0,
  },
  sources: [{ id: 1, portal_name: 'greenhouse', external_job_id: 'gh1', job_url: 'https://boards.greenhouse.io/rzp/1', apply_url: 'https://boards.greenhouse.io/rzp/1', seen_at: '2026-11-22T00:00:00Z' }],
};

describe('Comprehensive Frontend Pages & Drawer Tests', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = 'test-token';
    vi.restoreAllMocks();
  });

  it('JobQueuePage handles empty state, API errors, faceted filters, rescore, unhide, and Drawer actions', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes')) {
        return jsonResponse([{ id: 1, track_name: 'Backend Python', pdf_filename: 'be.pdf' }]);
      }
      if (url.includes('/api/v1/jobs/rescore')) {
        return jsonResponse({ rescored_count: 1 });
      }
      if (url.includes('/api/v1/jobs/101/status') && init?.method === 'PATCH') {
        return jsonResponse({ ...SAMPLE_JOB_CARD, hidden_by_gate1: false, hidden_reason: null });
      }
      if (url.includes('/api/v1/jobs/101')) {
        return jsonResponse({
          ...SAMPLE_JOB_CARD,
          description_raw: 'RAW_JD_CONTENT',
          boilerplate_stripped_text: 'CLEAN_JD_CONTENT',
          primary_skills_json: ['Python', 'Go'],
          secondary_skills_json: [],
          portal_signals_json: {},
          all_scores: [
            {
              resume_id: 1,
              track_name: 'Backend Python',
              pdf_filename: 'be.pdf',
              tier: 'A',
              is_winning_resume: true,
              semantic_bullet_coverage_pct: 78.0,
              matched_primary_skills_json: ['Python'],
              missing_primary_skills_json: ['Go'],
              missing_secondary_skills_json: [],
              bullet_proof_json: [
                { jd_requirement: 'Build FastAPI APIs', matched_bullet: 'Built FastAPI services', section_name: 'exp', similarity: 0.9, status: 'MATCHED' },
              ],
              cross_resume_alerts_json: [],
              scored_at: '2026-11-22T00:00:00Z',
            },
          ],
          sibling_jobs: [],
        });
      }
      if (url.includes('/api/v1/applications/cooldown/razorpay')) {
        return jsonResponse({ company_slug: 'razorpay', apps_last_30d: 0, max_company_apps_30d: 3, remaining_apps: 3, is_at_limit: false, next_slot_opens_at: null, warning_message: null });
      }
      if (url.includes('/api/v1/applications/draft') && init?.method === 'POST') {
        return jsonResponse({ id: 55, stage: 'draft' }, 201);
      }
      if (url.includes('/api/v1/applications/55/submit') && init?.method === 'POST') {
        return jsonResponse({ id: 55, stage: 'applied' }, 200);
      }
      if (url.includes('city=Mumbai')) {
        return jsonResponse({ total: 0, items: [] });
      }
      if (url.includes('only_hidden=true')) {
        return jsonResponse({
          total: 1,
          items: [{ ...SAMPLE_JOB_CARD, hidden_by_gate1: true, hidden_reason: 'Salary below threshold' }],
        });
      }
      return jsonResponse({ total: 1, items: [SAMPLE_JOB_CARD] });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<JobQueuePage />);

    expect(await screen.findByText('SDE II Payments')).toBeInTheDocument();

    // Faceted dropdowns & fresh checkbox
    await user.selectOptions(screen.getByLabelText('Resume Track Filter'), '1');
    await user.selectOptions(screen.getByLabelText('Missing Skills Max'), '1');
    await user.selectOptions(screen.getByLabelText('Apply Friction'), 'fast_apply');
    await user.click(screen.getByLabelText(/Fresh/i));
    await user.click(screen.getByRole('button', { name: /Re-score All/i }));

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes('/api/v1/jobs/rescore'))).toBe(true);
      expect(urls.some((u) => u.includes('resume_id=1') && u.includes('missing_max=1') && u.includes('friction=fast_apply') && u.includes('fresh_6h=true'))).toBe(true);
    });

    // Empty state via City search
    const cityInput = screen.getByPlaceholderText(/City \(e\.g\. Bengaluru\)/i);
    await user.type(cityInput, 'Mumbai');
    expect(await screen.findByText('No jobs match the current filters.')).toBeInTheDocument();
    await user.clear(cityInput);

    // Hidden Audit -> Unhide
    await user.click(screen.getByRole('button', { name: /Hidden Audit/i }));
    expect(await screen.findByText(/Salary below threshold/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Unhide' }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/v1/jobs/101/status'))).toBe(true);
    });

    // Open Drawer -> Start Draft -> Mark Applied -> Toggle Raw/Cleaned JD
    await user.click(screen.getByRole('button', { name: 'Active Queue' }));
    await user.click(await screen.findByText('SDE II Payments'));
    await user.click(await screen.findByRole('button', { name: /Start Draft/i }));
    expect(await screen.findByText(/Draft #55 created/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Mark Applied/i }));
    expect(await screen.findByText(/Submitted! Immutable snapshot saved/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Full \/ Cleaned JD/i }));
    expect(screen.getByText('CLEAN_JD_CONTENT')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Show Raw JD/i }));
    expect(screen.getByText('RAW_JD_CONTENT')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Close drawer'));
  });

  it('ApplicationsPage renders funnel + track gaps, transitions stages, submits drafts, and saves notes', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/applications/analytics')) {
        return jsonResponse({
          total_drafts: 1,
          total_submitted: 2,
          response_rate_pct: 50.0,
          stage_counts: { draft: 1, applied: 1, interview: 1 },
          track_skill_gaps: [
            { resume_id: 1, track_name: 'Backend Python', evaluated_ab_jobs: 4, top_missing_skills: [{ skill: 'Go', count: 3 }] },
          ],
        });
      }
      if (url.includes('/api/v1/applications/10/submit')) {
        return jsonResponse({ id: 10, stage: 'applied' });
      }
      if (url.includes('/api/v1/applications/10') && init?.method === 'PATCH') {
        return jsonResponse({ id: 10, stage: 'interview' });
      }
      return jsonResponse([
        {
          id: 10,
          job_id: 101,
          company_slug: 'razorpay',
          resume_id: 1,
          stage: 'draft',
          autofill_started_at: '2026-11-23T00:00:00Z',
          submitted_at: null,
          detection_method: 'extension',
          portal_used: 'greenhouse',
          jd_snapshot_text: '',
          resume_filename_snapshot: '',
          submitted_answers_json: {},
          recruiter_notes: '',
          job_title: 'SDE II',
          company_name: 'Razorpay',
          resume_track_name: 'Backend',
          cooldown: { company_slug: 'razorpay', apps_last_30d: 1, max_company_apps_30d: 3, remaining_apps: 2, is_at_limit: false, next_slot_opens_at: null, warning_message: null },
        },
      ]);
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<ApplicationsPage />);

    expect(await screen.findByText(/SDE II — Razorpay/)).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText(/Go \(3\)/)).toBeInTheDocument();

    // Update note & stage
    const noteInput = screen.getByPlaceholderText(/Recruiter notes/i);
    await user.type(noteInput, 'Strong round 1');
    await user.click(screen.getByRole('button', { name: 'Save Note' }));
    await user.selectOptions(screen.getByLabelText('Stage for application 10'), 'interview');
    await user.click(screen.getByRole('button', { name: 'Mark Submitted' }));

    await waitFor(() => {
      const methods = fetchMock.mock.calls.map((c) => `${c[1]?.method ?? 'GET'} ${c[0]}`);
      expect(methods.some((m) => m.includes('PATCH /api/v1/applications/10'))).toBe(true);
      expect(methods.some((m) => m.includes('POST /api/v1/applications/10/submit'))).toBe(true);
    });
  });

  it('FactVaultPage surfaces PII rejection banner and deletes Q&A rules cleanly', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/vault/qa-rules/8') && init?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204, json: async () => undefined } as Response);
      }
      if (url.includes('/api/v1/vault/qa-rules') && init?.method === 'POST') {
        return jsonResponse({ detail: 'Blocked sensitive PII question (pan_card)' }, 422);
      }
      if (url.includes('/api/v1/vault/qa-rules')) {
        return jsonResponse([
          { id: 8, normalized_question: 'notice period negotiable', canonical_aliases_json: [], verified_answer: 'Yes', answer_type: 'boolean', portal_scope: 'global', updated_at: '2026-11-23T00:00:00Z' },
        ]);
      }
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
        preferred_cities_json: ['Bengaluru'],
        willing_to_relocate: true,
        work_modes_json: ['hybrid'],
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
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<FactVaultPage />);

    expect(await screen.findByText('notice period negotiable')).toBeInTheDocument();

    // Attempt to save PAN -> displays backend 422 PII error message
    await user.type(screen.getByPlaceholderText(/Normalized question/i), 'PAN Card Number');
    await user.type(screen.getByPlaceholderText(/Verified answer/i), 'ABCDE1234F');
    await user.click(screen.getByRole('button', { name: /Add Rule/i }));

    expect(await screen.findByText(/Blocked sensitive PII question \(pan_card\)/)).toBeInTheDocument();

    // Delete existing Q&A rule
    await user.click(screen.getByLabelText('Delete rule 8'));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/v1/vault/qa-rules/8') && c[1]?.method === 'DELETE')).toBe(true);
    });
  });

  it('ResumesPage uploads PDF, views bullets, reparses, and deletes tracks', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes/1/reparse')) {
        return jsonResponse({
          id: 1,
          track_name: 'Backend Python',
          pdf_filename: 'be.pdf',
          bullet_count: 2,
          track_skills_json: ['Python', 'Kafka'],
          bullets: [
            { id: 11, section_name: 'Experience', bullet_text: 'Built Kafka pipelines in Python', extracted_skills_json: ['Python', 'Kafka'], has_embedding: true },
          ],
        });
      }
      if (url.includes('/api/v1/resumes/1') && init?.method === 'DELETE') {
        return Promise.resolve({ ok: true, status: 204, json: async () => undefined } as Response);
      }
      if (url.includes('/api/v1/resumes/1')) {
        return jsonResponse({
          id: 1,
          track_name: 'Backend Python',
          pdf_filename: 'be.pdf',
          bullet_count: 1,
          track_skills_json: ['Python', 'Kafka'],
          bullets: [
            { id: 11, section_name: 'Experience', bullet_text: 'Built Kafka pipelines in Python', extracted_skills_json: ['Python', 'Kafka'], has_embedding: true },
          ],
        });
      }
      if (url.includes('/api/v1/resumes') && init?.method === 'POST') {
        return jsonResponse({ id: 2, track_name: 'FullStack TS', bullet_count: 5 }, 201);
      }
      return jsonResponse([
        {
          id: 1,
          track_name: 'Backend Python',
          pdf_filename: 'be.pdf',
          target_titles_json: ['Backend Engineer'],
          search_locations_json: ['Bengaluru'],
          track_skills_json: ['Python', 'Kafka'],
          cover_template_text: '',
          is_active: true,
          bullet_count: 1,
          created_at: '2026-11-22T00:00:00Z',
        },
      ]);
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<ResumesPage />);

    expect(await screen.findByText('Backend Python')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Bullets' }));
    expect(await screen.findByText('Built Kafka pipelines in Python')).toBeInTheDocument();

    await user.click(screen.getByLabelText('Reparse resume'));
    expect(await screen.findByText(/Reparsed "Backend Python"/)).toBeInTheDocument();

    // Upload new resume PDF and submit form directly so jsdom constraint validation never blocks onSubmit
    await user.type(screen.getByPlaceholderText(/Track Name/i), 'FullStack TS');
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const pdf = new File(['%PDF-1.4'], 'fs.pdf', { type: 'application/pdf' });
    fireEvent.change(fileInput, { target: { files: [pdf] } });
    fireEvent.submit(fileInput.closest('form')!);
    expect(await screen.findByText(/Uploaded "FullStack TS"/)).toBeInTheDocument();

    await user.click(screen.getByLabelText('Delete resume'));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/v1/resumes/1') && c[1]?.method === 'DELETE')).toBe(true);
    });
  });

  it('CollectorsPage toggles manual Auto-Scheduler, runs ATS/JobSpy, verifies boards, and adds companies', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/collectors/scheduler/start')) {
        return jsonResponse({ running: true, interval_hours: 4 });
      }
      if (url.includes('/api/v1/collectors/scheduler/stop')) {
        return jsonResponse({ running: false, interval_hours: 4 });
      }
      if (url.includes('/api/v1/collectors/scheduler')) {
        return jsonResponse({ running: false, interval_hours: 4 });
      }
      if (url.includes('/api/v1/collectors/health')) {
        return jsonResponse({ total_sources: 68, healthy_sources: 67, cooldown_sources: 1, error_sources: 0, sources: [] });
      }
      if (url.includes('/api/v1/collectors/progress')) {
        return jsonResponse({ running: false, target: null, phase: 'idle', completed: 0, total: 0, current_item: null, fetched_so_far: 0, new_so_far: 0 });
      }
      if (url.includes('/api/v1/watchlist/verify')) {
        return jsonResponse({ total_checked: 68, valid_count: 66, invalid_count: 2, cooldown_count: 0, error_count: 0, results: [] });
      }
      if (url.includes('/api/v1/watchlist/razorpay')) {
        return jsonResponse({ slug: 'razorpay', is_watched: false });
      }
      if (url.includes('/api/v1/watchlist') && init?.method === 'POST') {
        return jsonResponse({ slug: 'zerodha', display_name: 'Zerodha', ats_type: 'greenhouse', is_watched: true, health_status: 'ok' }, 201);
      }
      if (url.includes('/api/v1/watchlist')) {
        return jsonResponse([
          { slug: 'razorpay', display_name: 'Razorpay', employer_type: 'direct_product', ats_type: 'greenhouse', ats_config_json: {}, is_watched: true, is_blacklisted: false, health_status: 'ok', last_polled_at: null },
        ]);
      }
      if (url.includes('/api/v1/collectors/run')) {
        return jsonResponse([{ status: 'started_in_background' }]);
      }
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<CollectorsPage />);

    expect(await screen.findByText('Razorpay')).toBeInTheDocument();
    expect(screen.getByText('68')).toBeInTheDocument();

    // Start & Stop manual scheduler
    await user.click(screen.getByRole('button', { name: /Start Auto-Scheduler/i }));
    expect(await screen.findByText(/Auto-scheduler started/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Stop Auto-Scheduler/i }));
    expect(await screen.findByText('Auto-scheduler stopped.')).toBeInTheDocument();

    // Trigger ATS Sweep & Verify Boards
    await user.click(screen.getByRole('button', { name: /Run ATS Sweep/i }));
    expect(await screen.findByText(/Started ats sweep/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Verify Boards/i }));
    expect(await screen.findByText(/Verified 68 boards: 66 OK, 2 invalid/)).toBeInTheDocument();

    // Add Watchlist company
    await user.type(screen.getByPlaceholderText(/slug/i), 'zerodha');
    await user.type(screen.getByPlaceholderText('Display Name'), 'Zerodha');
    await user.click(screen.getByRole('button', { name: /Add ATS Company/i }));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/api/v1/watchlist') && c[1]?.method === 'POST')).toBe(true);
    });
  });
});

