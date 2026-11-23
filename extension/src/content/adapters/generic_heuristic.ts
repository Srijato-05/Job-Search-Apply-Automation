import {
  attachResumePdf,
  extractFieldLabel,
  highlightAmberField,
  isSubmitLikeControl,
  selectNativeOrAriaOption,
  setNativeInputValue,
  withAutoSubmitShield,
} from '../dom_engine';
import { isBlockedPiiField } from '../pii_guard';
import type { AutofillContext, AutofillReport, PortalAdapter, QARuleItem, VaultFacts } from './types';

function normalizeQ(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9\s]/g, ' ').replace(/\s+/g, ' ').trim();
}

export function resolveFactAnswer(label: string, vault: VaultFacts): string | null {
  const l = label.toLowerCase();
  const fullName = (vault.full_name || '').trim();
  const nameParts = fullName.split(/\s+/).filter(Boolean);
  const firstName = nameParts[0] || '';
  const lastName = nameParts.length > 1 ? nameParts.slice(1).join(' ') : '';

  if (/\bfirst\s*name\b/.test(l)) return firstName || null;
  if (/\blast\s*name\b|\bsurname\b/.test(l)) return lastName || null;
  if (/\b(?:full\s*name|candidate\s*name|your\s*name)\b|^name\*?$/i.test(l.trim())) {
    return fullName || null;
  }
  if (/\bemail\b/.test(l)) return vault.email || null;
  if (/\b(?:phone|mobile|contact\s*number)\b/.test(l)) return vault.phone || null;
  if (/\blinkedin\b/.test(l)) return vault.linkedin_url || null;
  if (/\bgithub\b/.test(l)) return vault.github_url || null;
  if (/\b(?:portfolio|website|personal\s*site)\b/.test(l)) return vault.portfolio_url || null;

  if (/\b(?:current\s*ctc|current\s*salary|present\s*ctc|current\s*compensation)\b/.test(l)) {
    return vault.current_ctc_lpa ? String(vault.current_ctc_lpa) : null;
  }
  if (/\b(?:expected\s*ctc|expected\s*salary|expected\s*compensation|ectc)\b/.test(l)) {
    return vault.expected_ctc_lpa ? String(vault.expected_ctc_lpa) : null;
  }
  if (/\bnotice\s*period\b|\bdays\s*to\s*join\b/.test(l)) {
    return String(vault.notice_period_days ?? 0);
  }
  if (/\b(?:total\s*(?:years\s*of\s*)?experience|years\s*of\s*experience|relevant\s*experience)\b/.test(l)) {
    return String(vault.total_exp_years ?? 0);
  }
  if (/\b(?:current\s*city|current\s*location|city)\b/.test(l)) {
    return vault.current_city || null;
  }
  if (/\b(?:10th|tenth|ssc)\b/.test(l) && vault.tenth_pct != null) {
    return String(vault.tenth_pct);
  }
  if (/\b(?:12th|twelfth|hsc)\b/.test(l) && vault.twelfth_pct != null) {
    return String(vault.twelfth_pct);
  }

  return null;
}

export function resolveLearnedQaAnswer(label: string, qaRules: QARuleItem[]): string | null {
  const normLabel = normalizeQ(label);
  if (!normLabel) return null;

  for (const rule of qaRules) {
    const q = normalizeQ(rule.normalized_question);
    if (q && (normLabel === q || normLabel.includes(q) || q.includes(normLabel))) {
      return rule.verified_answer;
    }
    for (const alias of rule.canonical_aliases_json || []) {
      const a = normalizeQ(alias);
      if (a && (normLabel === a || normLabel.includes(a))) {
        return rule.verified_answer;
      }
    }
  }
  return null;
}

/**
 * Shared deterministic DOM autofill engine scoped to a root container (defaults to document).
 * Strictly enforces PII blocking, Amber Pause-and-Learn for unknowns, and NEVER auto-submits.
 */
export function runHeuristicAutofill(
  ctx: AutofillContext,
  options: {
    portalName: string;
    adapterName: string;
    containerSelector?: string;
    fileInputSelector?: string;
  },
): AutofillReport {
  const { document: doc, vault, qaRules, resumePdf } = ctx;
  return withAutoSubmitShield(doc, () => {
    const root: ParentNode =
      (options.containerSelector && doc.querySelector(options.containerSelector)) || doc;

    const filledFields: string[] = [];
    const blockedPiiFields: string[] = [];
    const unknownFields: { question: string; fieldTag: string }[] = [];
    let resumeAttached = false;

    // 1. Handle resume file upload inputs first (strictly skip images, cover letters, photos, IDs)
    if (resumePdf) {
      const fileSelector = options.fileInputSelector || 'input[type="file"]';
      const fileInputs = Array.from(root.querySelectorAll(fileSelector)) as HTMLInputElement[];
      for (const fi of fileInputs) {
        const accept = (fi.getAttribute('accept') || '').toLowerCase();
        const lbl = extractFieldLabel(doc, fi);
        if (accept.includes('image/')) continue;
        if (/\b(?:cover\s*letter|photo|avatar|picture|selfie|signature|id\s*proof)\b/i.test(lbl)) {
          continue;
        }
        if (attachResumePdf(fi, resumePdf)) {
          resumeAttached = true;
          filledFields.push(lbl || 'Resume PDF');
          break;
        }
      }
    }

    // 2. Process all text / number / email / tel / url / textarea / select fields
    const controls = Array.from(
      root.querySelectorAll('input, textarea, select'),
    ) as (HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement)[];

    for (const el of controls) {
      if (isSubmitLikeControl(el)) {
        continue;
      }
      if (el.tagName === 'INPUT') {
        const t = ((el as HTMLInputElement).type || 'text').toLowerCase();
        if (['hidden', 'submit', 'button', 'reset', 'image', 'file'].includes(t)) {
          continue;
        }
      }
      if ((el as HTMLInputElement).disabled || (el as HTMLInputElement).readOnly) {
        continue;
      }

      const label = extractFieldLabel(doc, el).trim();
      if (!label) continue;

      // Strict PII check — NEVER autofill government IDs, DoB, bank, etc.
      if (isBlockedPiiField(label)) {
        blockedPiiFields.push(label);
        continue;
      }

      const answer = resolveFactAnswer(label, vault) ?? resolveLearnedQaAnswer(label, qaRules);
      if (answer !== null) {
        if (el.tagName === 'SELECT') {
          if (selectNativeOrAriaOption(doc, el, answer)) {
            filledFields.push(label);
          }
        } else {
          setNativeInputValue(el as HTMLInputElement | HTMLTextAreaElement, answer);
          filledFields.push(label);
        }
      } else if (!el.value?.trim()) {
        // Flag unknown field in Amber for Pause-and-Learn
        highlightAmberField(el, label);
        unknownFields.push({ question: label, fieldTag: el.tagName.toLowerCase() });
      }
    }

    // NEVER auto-click Submit
    return {
      portalName: options.portalName,
      adapterName: options.adapterName,
      filledFields,
      blockedPiiFields,
      unknownFields,
      resumeAttached,
      pausedBeforeSubmit: true,
    };
  });
}

export const genericHeuristicAdapter: PortalAdapter = {
  name: 'generic_heuristic',
  portalName: 'generic',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'generic',
      adapterName: 'generic_heuristic',
    });
  },
};

