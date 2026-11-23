import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const linkedinAdapter: PortalAdapter = {
  name: 'linkedin',
  portalName: 'linkedin',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'linkedin',
      adapterName: 'linkedin',
      containerSelector: '.jobs-easy-apply-modal, .artdeco-modal, form',
      fileInputSelector: 'input[type="file"]',
    });
  },
};

