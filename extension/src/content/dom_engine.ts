export interface PdfFilePayload {
  filename: string;
  bytes: number[];
}

/**
 * Resolve human-readable label for a form control using aria-label, <label>, container text, or name.
 */
export function extractFieldLabel(doc: Document, el: Element): string {
  const aria = el.getAttribute('aria-label');
  if (aria?.trim()) return aria.trim();

  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) {
    const parts = labelledBy
      .split(/\s+/)
      .map((id) => doc.getElementById(id)?.textContent?.trim() ?? '')
      .filter(Boolean);
    if (parts.length > 0) return parts.join(' ');
  }

  const id = el.getAttribute('id');
  if (id) {
    const safeId =
      typeof CSS !== 'undefined' && typeof CSS.escape === 'function'
        ? CSS.escape(id)
        : id.replace(/([^\w-])/g, '\\$1');
    const labelEl = doc.querySelector(`label[for="${safeId}"]`);
    if (labelEl?.textContent?.trim()) return labelEl.textContent.trim();
  }

  const wrappingLabel = el.closest('label');
  if (wrappingLabel?.textContent?.trim()) return wrappingLabel.textContent.trim();

  const container = el.closest(
    '.field, .form-group, .application-question, [data-automation-id], .fb-dash-form-element, .jobs-easy-apply-form-section__grouping',
  );
  const containerLabel = container?.querySelector('label, .label, legend, [data-automation-id*="label"]');
  if (containerLabel?.textContent?.trim()) return containerLabel.textContent.trim();

  const placeholder = el.getAttribute('placeholder');
  if (placeholder?.trim()) return placeholder.trim();

  return el.getAttribute('name') || el.getAttribute('data-automation-id') || id || '';
}

/**
 * Set value on React / Angular controlled inputs using the native prototype setter + bubbling events.
 */
export function setNativeInputValue(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string,
): void {
  const proto =
    el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
  if (descriptor?.set) {
    descriptor.set.call(el, value);
  } else {
    el.value = value;
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur', { bubbles: true }));
}

const SUBMIT_CONTROL_RE =
  /\b(?:submit(?:[\s_-]+(?:application|form|now))?|apply[\s_-]+now|easy[\s_-]+apply|send[\s_-]+application|confirm[\s_-]+(?:and[\s_-]+)?(?:submit|apply)|complete[\s_-]+application|finish[\s_-]+application|final[\s_-]+submit)\b/i;

/**
 * Hard guard identifying any button, input, or ARIA trigger that could submit or apply.
 */
export function isSubmitLikeControl(el: Element | null | undefined): boolean {
  if (!el) return false;
  if (el.getAttribute('type')?.toLowerCase() === 'submit') return true;
  if (typeof el.closest === 'function' && el.closest('button[type="submit"], input[type="submit"]')) {
    return true;
  }
  const probe = [
    el.textContent ?? '',
    el.getAttribute('value') ?? '',
    el.getAttribute('aria-label') ?? '',
    el.getAttribute('name') ?? '',
    el.getAttribute('data-automation-id') ?? '',
    el.getAttribute('id') ?? '',
  ]
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
  return Boolean(probe && SUBMIT_CONTROL_RE.test(probe));
}

/**
 * Capture-phase shield cancelling any accidental `submit` or submit-button `click` while autofill runs.
 * Automatically removed in `finally` so the human can submit manually after reviewing.
 */
export function withAutoSubmitShield<T>(doc: Document, fn: () => T): T {
  const blockSubmit = (ev: Event) => {
    ev.preventDefault();
    ev.stopImmediatePropagation();
  };
  const blockSubmitClick = (ev: Event) => {
    const target = ev.target as Element | null;
    if (isSubmitLikeControl(target)) {
      ev.preventDefault();
      ev.stopImmediatePropagation();
    }
  };
  doc.addEventListener('submit', blockSubmit, true);
  doc.addEventListener('click', blockSubmitClick, true);
  try {
    return fn();
  } finally {
    doc.removeEventListener('submit', blockSubmit, true);
    doc.removeEventListener('click', blockSubmitClick, true);
  }
}

/**
 * Select an option in a native <select> or ARIA combobox/listbox widget.
 */
export function selectNativeOrAriaOption(doc: Document, el: Element, targetValue: string): boolean {
  if (isSubmitLikeControl(el)) return false;
  const target = targetValue.trim().toLowerCase();
  if (!target) return false;

  if (el.tagName === 'SELECT') {
    const selectEl = el as HTMLSelectElement;
    const match = Array.from(selectEl.options).find(
      (opt) =>
        opt.value.trim().toLowerCase() === target ||
        opt.textContent?.trim().toLowerCase().includes(target),
    );
    if (!match) return false;
    const descriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    if (descriptor?.set) {
      descriptor.set.call(selectEl, match.value);
    } else {
      selectEl.value = match.value;
    }
    selectEl.dispatchEvent(new Event('change', { bubbles: true }));
    selectEl.dispatchEvent(new Event('blur', { bubbles: true }));
    return true;
  }

  // ARIA listbox / combobox fallback (never clicks submit-like triggers or options)
  if (el instanceof HTMLElement && !isSubmitLikeControl(el)) {
    el.click();
    const options = Array.from(doc.querySelectorAll('[role="option"]'));
    const match = options.find((opt) =>
      (opt.textContent ?? '').trim().toLowerCase().includes(target),
    );
    if (match instanceof HTMLElement && !isSubmitLikeControl(match)) {
      match.click();
      return true;
    }
  }
  return false;
}

/**
 * Inject a verified resume PDF File into `<input type="file">` via DataTransfer.
 */
export function attachResumePdf(fileInput: HTMLInputElement, pdf: PdfFilePayload): boolean {
  const file = new File([new Uint8Array(pdf.bytes)], pdf.filename, {
    type: 'application/pdf',
  });

  if (typeof DataTransfer !== 'undefined') {
    const dt = new DataTransfer();
    dt.items.add(file);
    try {
      fileInput.files = dt.files;
    } catch {
      Object.defineProperty(fileInput, 'files', {
        value: dt.files,
        configurable: true,
      });
    }
  } else {
    // Fallback for lightweight DOM test environments without global DataTransfer
    const fileListLike = {
      0: file,
      length: 1,
      item: (idx: number) => (idx === 0 ? file : null),
    } as unknown as FileList;
    Object.defineProperty(fileInput, 'files', {
      value: fileListLike,
      configurable: true,
    });
  }

  fileInput.dispatchEvent(new Event('input', { bubbles: true }));
  fileInput.dispatchEvent(new Event('change', { bubbles: true }));
  return Boolean(fileInput.files && fileInput.files.length > 0);
}

/**
 * Visually mark unknown required/screening inputs with Amber highlighting for Pause-and-Learn.
 */
export function highlightAmberField(el: HTMLElement, questionLabel: string): void {
  el.style.outline = '2px solid #d97706';
  el.style.backgroundColor = 'rgba(245, 158, 11, 0.10)';
  el.setAttribute('data-jobautomation-amber', 'true');
  el.setAttribute('data-jobautomation-question', questionLabel);
}
