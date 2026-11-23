import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const smartrecruitersAdapter: PortalAdapter = {
  name: 'smartrecruiters',
  portalName: 'smartrecruiters',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'smartrecruiters',
      adapterName: 'smartrecruiters',
      containerSelector: 'oc-apply-form, form',
    });
  },
};

