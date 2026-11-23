export type WatcherEventType =
  | 'SUBMIT_CLICKED'
  | 'CONFIRMATION_SEEN'
  | 'NATIVE_APPLIED_DETECTED'
  | 'EXPIRED_DETECTED';

export interface WatcherEvent {
  type: WatcherEventType;
  detail: string;
}

const CONFIRMATION_RE =
  /\b(application\s+(?:has\s+been\s+)?(?:submitted|received)|thank\s+you\s+for\s+applying|thanks\s+for\s+applying|successfully\s+applied)\b/i;

const EXPIRED_RE =
  /\b(no\s+longer\s+accepting\s+applications|job\s+(?:has\s+)?expired|job\s+is\s+no\s+longer\s+available|position\s+has\s+been\s+filled|posting\s+(?:has\s+)?closed)\b/i;

const APPLIED_BADGE_RE = /^\s*(?:applied(?:\s+on\b.*)?|already\s+applied|application\s+submitted)\s*$/i;

/**
 * Detect native portal "Applied" / "Application Submitted" badges.
 */
export function detectNativeAppliedBadge(doc: Document): boolean {
  if (
    doc.querySelector(
      '.jobs-s-apply--applied, [data-applied="true"], .artdeco-inline-feedback--success',
    )
  ) {
    return true;
  }

  const candidates = doc.querySelectorAll('button, span, div.badge, .applied-status, [class*="applied"]');
  for (const el of Array.from(candidates)) {
    const txt = (el.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (txt.length <= 60 && APPLIED_BADGE_RE.test(txt)) {
      return true;
    }
  }
  return false;
}

/**
 * Detect post-submit confirmation banners or thank-you pages.
 */
export function detectConfirmationScreen(doc: Document): boolean {
  const candidates = doc.querySelectorAll('h1, h2, h3, [role="status"], [role="alert"], .confirmation, main');
  for (const el of Array.from(candidates)) {
    const txt = (el.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (txt && txt.length <= 400 && CONFIRMATION_RE.test(txt)) {
      return true;
    }
  }
  return CONFIRMATION_RE.test((doc.body?.textContent ?? '').slice(0, 4000));
}

/**
 * Detect closed / expired portal listings ("No longer accepting applications", etc.).
 */
export function detectExpiredPosting(doc: Document): boolean {
  const candidates = doc.querySelectorAll(
    '.jobs-details-top-card__apply-error, .closed-job, [role="alert"], h1, h2, p, span',
  );
  for (const el of Array.from(candidates)) {
    const txt = (el.textContent ?? '').replace(/\s+/g, ' ').trim();
    if (txt && txt.length <= 200 && EXPIRED_RE.test(txt)) {
      return true;
    }
  }
  return false;
}

/**
 * Observe submit clicks, confirmation transitions, native applied badges, and expired notices.
 */
export function attachSubmitWatcher(
  doc: Document,
  onEvent: (event: WatcherEvent) => void,
): () => void {
  const emitted = new Set<WatcherEventType>();
  const emitOnce = (type: WatcherEventType, detail: string) => {
    if (emitted.has(type)) return;
    emitted.add(type);
    onEvent({ type, detail });
  };

  const scanDom = () => {
    if (detectExpiredPosting(doc)) {
      emitOnce('EXPIRED_DETECTED', 'Portal indicates job is closed or expired');
    }
    if (detectConfirmationScreen(doc)) {
      emitOnce('CONFIRMATION_SEEN', 'Application confirmation screen detected');
    } else if (detectNativeAppliedBadge(doc)) {
      emitOnce('NATIVE_APPLIED_DETECTED', 'Portal native Applied badge detected');
    }
  };

  const onClick = (ev: Event) => {
    const target = ev.target as Element | null;
    const btn = target?.closest?.('button, input[type="submit"]');
    if (!btn) return;
    const label = ((btn as HTMLInputElement).value || btn.textContent || '').trim();
    const isSubmitType = btn.getAttribute('type') === 'submit';
    if (isSubmitType || /\bsubmit(?:\s+application)?\b/i.test(label)) {
      emitOnce('SUBMIT_CLICKED', `Clicked submit control: ${label || 'submit'}`);
    }
  };

  doc.addEventListener('click', onClick, true);
  scanDom();

  let observer: MutationObserver | null = null;
  if (typeof MutationObserver !== 'undefined' && doc.body) {
    observer = new MutationObserver(() => scanDom());
    observer.observe(doc.body, { childList: true, subtree: true });
  }

  return () => {
    doc.removeEventListener('click', onClick, true);
    observer?.disconnect();
  };
}

