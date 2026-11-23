export interface JobSourceItem {
  id: number;
  portal_name: string;
  external_job_id: string | null;
  job_url: string;
  apply_url: string;
  seen_at: string;
}

export interface WinningScoreSummary {
  resume_id: number;
  track_name: string;
  pdf_filename: string;
  tier: string;
  semantic_bullet_coverage_pct: number;
  matched_primary_skills_json: string[];
  missing_primary_skills_json: string[];
  missing_secondary_skills_json: string[];
  cross_resume_alerts_count: number;
}

export interface BulletProofEntry {
  jd_requirement: string;
  matched_bullet: string | null;
  section_name: string | null;
  similarity: number;
  status: 'MATCHED' | 'GAP' | string;
}

export interface CrossResumeAlert {
  jd_requirement: string;
  other_resume_id: number;
  other_resume_track: string;
  other_resume_pdf: string;
  matching_bullet: string;
  similarity: number;
}

export interface JobResumeScoreDetail {
  resume_id: number;
  track_name: string;
  pdf_filename: string;
  tier: string;
  is_winning_resume: boolean;
  semantic_bullet_coverage_pct: number;
  matched_primary_skills_json: string[];
  missing_primary_skills_json: string[];
  missing_secondary_skills_json: string[];
  bullet_proof_json: BulletProofEntry[];
  cross_resume_alerts_json: CrossResumeAlert[];
  scored_at: string;
}

export interface SiblingJobSummary {
  id: number;
  title: string;
  role_subtag: string;
  req_id: string | null;
  normalized_city: string;
  status: string;
}

export interface JobCard {
  id: number;
  title: string;
  company_name: string;
  company_slug: string;
  role_subtag: string;
  req_id: string | null;
  normalized_city: string;
  office_locality: string;
  work_mode: string;
  exp_min_years: number | null;
  exp_max_years: number | null;
  salary_min_lpa: number | null;
  salary_max_lpa: number | null;
  max_notice_days: number | null;
  notice_compatible: boolean;
  apply_friction: string;
  employer_type: string;
  hidden_by_gate1: boolean;
  hidden_reason: string | null;
  status: string;
  parent_sibling_job_id: number | null;
  repost_count: number;
  posted_at: string | null;
  first_seen_at: string;
  last_reposted_at: string;
  winning_score: WinningScoreSummary | null;
  sources: JobSourceItem[];
}

export interface JobListResponse {
  total: number;
  items: JobCard[];
}

export interface JobDetail extends JobCard {
  description_raw: string;
  boilerplate_stripped_text: string;
  primary_skills_json: string[];
  secondary_skills_json: string[];
  portal_signals_json: Record<string, unknown>;
  all_scores: JobResumeScoreDetail[];
  sibling_jobs: SiblingJobSummary[];
}

export interface JobDiffResponse {
  job_a_id: number;
  job_b_id: number;
  job_a_subtag: string;
  job_b_subtag: string;
  similarity_pct: number;
  shared_skills: string[];
  only_in_job_a_skills: string[];
  only_in_job_b_skills: string[];
  unchanged_lines: string[];
  removed_lines: string[];
  added_lines: string[];
}

export interface CooldownStatus {
  company_slug: string;
  apps_last_30d: number;
  max_company_apps_30d: number;
  remaining_apps: number;
  is_at_limit: boolean;
  next_slot_opens_at: string | null;
  warning_message: string | null;
}

export interface ApplicationRecord {
  id: number;
  job_id: number | null;
  company_slug: string;
  resume_id: number | null;
  stage: string;
  autofill_started_at: string | null;
  submitted_at: string | null;
  detection_method: string;
  portal_used: string;
  jd_snapshot_text: string;
  resume_filename_snapshot: string;
  submitted_answers_json: Record<string, unknown>;
  recruiter_notes: string;
  job_title: string | null;
  company_name: string | null;
  resume_track_name: string | null;
  cooldown: CooldownStatus | null;
}

export interface FactVaultData {
  id?: number;
  full_name: string;
  email: string;
  phone: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  leetcode_url: string;
  current_ctc_lpa: number;
  current_fixed_lpa: number;
  current_variable_lpa: number;
  expected_ctc_lpa: number;
  min_acceptable_hike_pct: number;
  notice_period_days: number;
  serving_notice: boolean;
  last_working_day: string | null;
  notice_negotiable: boolean;
  min_negotiable_days: number | null;
  total_exp_years: number;
  relevant_exp_years: number;
  skill_years_json: Record<string, number>;
  current_city: string;
  hometown: string;
  preferred_cities_json: string[];
  willing_to_relocate: boolean;
  work_modes_json: string[];
  open_to_rotational_shifts: boolean;
  tenth_pct: number | null;
  tenth_board: string;
  tenth_year: number | null;
  twelfth_pct: number | null;
  twelfth_board: string;
  twelfth_year: number | null;
  education_history_json: Record<string, unknown>[];
  active_backlogs: number;
  work_history_json: Record<string, unknown>[];
  negative_keywords_json: string[];
  company_blacklist_json: string[];
  max_company_apps_30d: number;
  updated_at?: string;
}

export interface QARuleItem {
  id: number;
  normalized_question: string;
  canonical_aliases_json: string[];
  verified_answer: string;
  answer_type: string;
  portal_scope: string;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResumeBullet {
  id: number;
  section_name: string;
  bullet_order: number;
  bullet_text: string;
  extracted_skills_json: string[];
  has_embedding: boolean;
}

export interface ResumeSummary {
  id: number;
  track_name: string;
  pdf_filename: string;
  pdf_sha256: string;
  target_titles_json: string[];
  search_locations_json: string[];
  track_skills_json: string[];
  cover_template: string;
  is_active: boolean;
  bullet_count: number;
  created_at: string;
  updated_at: string;
}

export interface ResumeDetail extends ResumeSummary {
  raw_text: string;
  bullets: ResumeBullet[];
}

export interface WatchedCompany {
  id: number;
  slug: string;
  display_name: string;
  employer_type: string;
  ats_type: string | null;
  ats_config_json: Record<string, unknown>;
  is_watched: boolean;
  is_blacklisted: boolean;
  health_status: string;
  last_polled_at: string | null;
}

export interface SourceHealthItem {
  source_key: string;
  source_type: string;
  display_name: string;
  ats_type: string | null;
  status: string;
  last_polled_at: string | null;
  cooldown_until: string | null;
  last_fetched_count: number;
  last_new_count: number;
  last_error: string | null;
}

export interface CollectorHealthResponse {
  total_sources: number;
  healthy_sources: number;
  cooldown_sources: number;
  error_sources: number;
  sources: SourceHealthItem[];
}

export interface CollectorProgress {
  running: boolean;
  target: string | null;
  phase: string;
  completed: number;
  total: number;
  current_item: string | null;
  fetched_so_far: number;
  new_so_far: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface WatchlistVerifyResponse {
  total_checked: number;
  valid_count: number;
  invalid_count: number;
  cooldown_count: number;
  error_count: number;
}

export interface AnalyticsSummary {
  total_drafts: number;
  total_submitted: number;
  response_rate_pct: number;
  stage_counts: Record<string, number>;
  track_skill_gaps: {
    resume_id: number;
    track_name: string;
    evaluated_ab_jobs: number;
    top_missing_skills: { skill: string; count: number }[];
  }[];
}
