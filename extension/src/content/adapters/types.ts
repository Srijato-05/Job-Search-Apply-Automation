import type { PdfFilePayload } from '../dom_engine';

export interface VaultFacts {
  full_name: string;
  email: string;
  phone: string;
  linkedin_url: string;
  github_url: string;
  portfolio_url: string;
  current_ctc_lpa: number;
  expected_ctc_lpa: number;
  notice_period_days: number;
  serving_notice?: boolean;
  min_negotiable_days?: number | null;
  total_exp_years: number;
  relevant_exp_years?: number;
  current_city: string;
  willing_to_relocate?: boolean;
  tenth_pct?: number | null;
  twelfth_pct?: number | null;
}

export interface QARuleItem {
  id?: number;
  normalized_question: string;
  canonical_aliases_json: string[];
  verified_answer: string;
}

export interface AutofillContext {
  document: Document;
  pageUrl: string;
  vault: VaultFacts;
  qaRules: QARuleItem[];
  resumePdf?: PdfFilePayload | null;
}

export interface UnknownFieldPrompt {
  question: string;
  fieldTag: string;
}

export interface AutofillReport {
  portalName: string;
  adapterName: string;
  filledFields: string[];
  blockedPiiFields: string[];
  unknownFields: UnknownFieldPrompt[];
  resumeAttached: boolean;
  pausedBeforeSubmit: true;
}

export interface PortalAdapter {
  name: string;
  portalName: string;
  run(ctx: AutofillContext): AutofillReport;
}

