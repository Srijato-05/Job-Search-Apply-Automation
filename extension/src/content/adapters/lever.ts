import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const leverAdapter: PortalAdapter = {
  name: 'lever',
  portalName: 'lever',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'lever',
      adapterName: 'lever',
      containerSelector: '.application-form, form',
      fileInputSelector: 'input[type="file"][name="resume"], input[type="file"]',
    });
  },
};

