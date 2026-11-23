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

describe('JobAutomation Dashboard (Cycle 5)', () => {
  beforeEach(() => {
    window.__JOB_AUTOMATION_TOKEN__ = 'test-local-token';
    vi.restoreAllMocks();
  });

  it('renders Job Queue, binds FTS5 search & tier filter, and toggles Hidden Audit tab', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes')) {
        return jsonResponse([{ id: 1, track_name: 'Backend Python', pdf_filename: 'be.pdf' }]);
      }
      if (url.includes('/api/v1/jobs')) {
        return jsonResponse({
          total: 1,
          items: [
            {
              id: 101,
              title: 'SDE II Payments',
              company_name: 'Razorpay',
              company_slug: 'razorpay',
              role_subtag: 'Payments • Python / Kafka',
              req_id: 'JR9001',
              normalized_city: 'Bengaluru',
              office_locality: 'Koramangala',
              work_mode: 'hybrid',
              exp_min_years: 3,
              exp_max_years: 5,
              salary_min_lpa: 30,
              salary_max_lpa: 45,
              max_notice_days: 30,
              notice_compatible: true,
              apply_friction: 'fast_apply',
              employer_type: 'direct_product',
              hidden_by_gate1: url.includes('only_hidden=true'),
              hidden_reason: url.includes('only_hidden=true') ? 'Notice exceeds limit' : null,
              status: 'active',
              parent_sibling_job_id: null,
              repost_count: 1,
              posted_at: null,
              first_seen_at: '2026-11-22T00:00:00Z',
              last_reposted_at: '2026-11-22T00:00:00Z',
              winning_score: {
                resume_id: 1,
                track_name: 'Backend Python',
                pdf_filename: 'be.pdf',
                tier: 'S',
                semantic_bullet_coverage_pct: 88.5,
                matched_primary_skills_json: ['Python', 'Kafka'],
                missing_primary_skills_json: [],
                missing_secondary_skills_json: [],
                cross_resume_alerts_count: 1,
              },
              sources: [],
            },
          ],
        });
      }
      return jsonResponse({});
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText('SDE II Payments')).toBeInTheDocument();
    expect(screen.getByText(/Tier S • 88\.5%/)).toBeInTheDocument();

    // FTS5 search + Tier S filter
    await user.click(screen.getByRole('button', { name: 'Tier S' }));
    const searchInput = screen.getByPlaceholderText(/FTS5 Boolean search/i);
    await user.type(searchInput, 'Python AND Kafka');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => {
      const calledUrls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(calledUrls.some((u) => u.includes('tier=S') && u.includes('fts_query=Python+AND+Kafka'))).toBe(true);
    });

    // Switch to Hidden Audit tab
    await user.click(screen.getByRole('button', { name: /Hidden Audit/i }));
    expect(await screen.findByText(/Notice exceeds limit/)).toBeInTheDocument();
  });

  it('opens JobDetailDrawer with Option 1+3 Proof Table, Cross-Resume Alert, and Sibling JD Diff', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes')) return jsonResponse([]);
      if (url.includes('/api/v1/jobs/101/diff/102')) {
        return jsonResponse({
          job_a_id: 101,
          job_b_id: 102,
          job_a_subtag: 'Payments • Python',
          job_b_subtag: 'Frontend • React',
          similarity_pct: 32.0,
          shared_skills: ['Git'],
          only_in_job_a_skills: ['Python'],
          only_in_job_b_skills: ['React'],
          unchanged_lines: ['Bengaluru office'],
          removed_lines: ['Build FastAPI payment workers'],
          added_lines: ['Build React merchant dashboards'],
        });
      }
      if (url.includes('/api/v1/jobs/101')) {
        return jsonResponse({
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
          salary_min_lpa: 30,
          salary_max_lpa: 45,
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
          winning_score: {
            resume_id: 1,
            track_name: 'Backend Python',
            pdf_filename: 'be.pdf',
            tier: 'A',
            semantic_bullet_coverage_pct: 75.0,
            matched_primary_skills_json: ['Python'],
            missing_primary_skills_json: ['Go'],
            missing_secondary_skills_json: [],
            cross_resume_alerts_count: 1,
          },
          sources: [],
          description_raw: 'Raw JD text',
          boilerplate_stripped_text: 'Clean JD text',
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
              semantic_bullet_coverage_pct: 75.0,
              matched_primary_skills_json: ['Python'],
              missing_primary_skills_json: ['Go'],
              missing_secondary_skills_json: [],
              bullet_proof_json: [
                {
                  jd_requirement: 'Build FastAPI payment workers',
                  matched_bullet: 'Architected async Kafka & FastAPI consumers',
                  section_name: 'experience',
                  similarity: 0.89,
                  status: 'MATCHED',
                },
              ],
              cross_resume_alerts_json: [
                {
                  jd_requirement: 'Production Go microservices',
                  other_resume_id: 2,
                  other_resume_track: 'Systems Go',
                  other_resume_pdf: 'go.pdf',
                  matching_bullet: 'Built low-latency Go gRPC proxy',
                  similarity: 0.86,
                },
              ],
              scored_at: '2026-11-22T00:00:00Z',
            },
          ],
          sibling_jobs: [
            { id: 102, title: 'SDE II', role_subtag: 'Frontend • React', req_id: 'JR9002', normalized_city: 'Bengaluru', status: 'active' },
          ],
        });
      }
      if (url.includes('/api/v1/applications/cooldown/razorpay')) {
        return jsonResponse({
          company_slug: 'razorpay',
          apps_last_30d: 1,
          max_company_apps_30d: 3,
          remaining_apps: 2,
          is_at_limit: false,
          next_slot_opens_at: null,
          warning_message: null,
        });
      }
      return jsonResponse({
        total: 1,
        items: [
          {
            id: 101,
            title: 'SDE II Payments',
            company_name: 'Razorpay',
            company_slug: 'razorpay',
            role_subtag: 'Payments • Python',
            req_id: 'JR9001',
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
          },
        ],
      });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByText('SDE II Payments'));

    expect(await screen.findByText(/Architected async Kafka & FastAPI consumers/)).toBeInTheDocument();
    expect(screen.getByText(/Built low-latency Go gRPC proxy/)).toBeInTheDocument();
    expect(screen.getByText(/30d Cooldown: 1\/3 submitted/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Sibling JD Diff/i }));
    expect(await screen.findByText(/\+ Build React merchant dashboards/)).toBeInTheDocument();
  });

  it('displays Offline Snapshot viewer in ApplicationsPage and saves FactVaultPage', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/api/v1/resumes')) return jsonResponse([]);
      if (url.includes('/api/v1/applications/analytics')) {
        return jsonResponse({
          total_drafts: 0,
          total_submitted: 1,
          response_rate_pct: 0,
          stage_counts: { applied: 1 },
          track_skill_gaps: [],
        });
      }
      if (url.includes('/api/v1/applications')) {
        return jsonResponse([
          {
            id: 7,
            job_id: null,
            company_slug: 'cred',
            resume_id: 1,
            stage: 'applied',
            autofill_started_at: '2026-11-21T10:00:00Z',
            submitted_at: '2026-11-21T10:05:00Z',
            detection_method: 'extension_submit',
            portal_used: 'greenhouse',
            jd_snapshot_text: 'Frozen CRED Backend Snapshot JD',
            resume_filename_snapshot: 'Backend_Python.pdf',
            submitted_answers_json: { notice_period: '30 days' },
            recruiter_notes: 'Referral submitted',
            job_title: null,
            company_name: null,
            resume_track_name: 'Backend Python',
            cooldown: null,
          },
        ]);
      }
      if (url.includes('/api/v1/vault/qa-rules')) return jsonResponse([]);
      if (url.includes('/api/v1/vault') && init?.method === 'PUT') {
        return jsonResponse(JSON.parse(String(init.body)));
      }
      if (url.includes('/api/v1/vault')) {
        return jsonResponse({
          full_name: 'Aarav Sharma',
          email: 'aarav@example.com',
          phone: '+91-9876543210',
          linkedin_url: '',
          github_url: '',
          portfolio_url: '',
          leetcode_url: '',
          current_ctc_lpa: 22,
          current_fixed_lpa: 20,
          current_variable_lpa: 2,
          expected_ctc_lpa: 32,
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
          preferred_cities_json: ['Bengaluru', 'Hyderabad'],
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
      }
      return jsonResponse({ total: 0, items: [] });
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(<App />);

    // Applications CRM + Offline Snapshot
    await user.click(screen.getByRole('button', { name: /Applications CRM/i }));
    expect(await screen.findByText(/Snapshot: Backend_Python.pdf/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /View Offline Snapshot/i }));
    expect(await screen.findByText('Frozen CRED Backend Snapshot JD')).toBeInTheDocument();

    // Fact Vault save
    await user.click(screen.getByRole('button', { name: /Fact Vault & Backup/i }));
    expect(await screen.findByDisplayValue('Aarav Sharma')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Save Fact Vault/i }));
    expect(await screen.findByText('Fact Vault saved.')).toBeInTheDocument();
  });
});

