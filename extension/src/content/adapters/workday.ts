import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const workdayAdapter: PortalAdapter = {
  name: 'workday',
  portalName: 'workday',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'workday',
      adapterName: 'workday',
      containerSelector: '[data-automation-id="jobApplication"], [data-automation-id="applyManually"], form',
      fileInputSelector: '[data-automation-id="file-upload-input-ref"], input[type="file"]',
    });
  },
};

