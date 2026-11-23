/**
 * Client-side PII guardrail mirroring backend/app/vault/pii_guard.py.
 * Sensitive government IDs, DoB, and banking fields are ALWAYS blocked from autofill & Q&A storage.
 */
const BLOCKED_PII_PATTERNS: RegExp[] = [
  /\bpan\b(?:\s*(?:card|no|number))?/i,
  /\baadhaar\b|\baadhar\b|\buidai\b/i,
  /\bpassport\b(?:\s*(?:no|number|expiry))?/i,
  /\b(?:date\s+of\s+birth|d\.?o\.?b\.?|birth\s*date)\b/i,
  /\bbank\s*(?:account|a\/c|acc)\b|\bifsc\b|\bmicr\b/i,
  /\buan\b|\bpf\s*(?:account|number)\b|\bepfo\b/i,
  /\bssn\b|\bsocial\s+security\b/i,
  /\bdriving\s+licen[sc]e\b|\bvoter\s*id\b/i,
];

export function isBlockedPiiField(labelText: string): boolean {
  const cleaned = labelText.replace(/\s+/g, ' ').trim();
  if (!cleaned) return false;
  return BLOCKED_PII_PATTERNS.some((re) => re.test(cleaned));
}

