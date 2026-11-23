import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const founditAdapter: PortalAdapter = {
  name: 'foundit',
  portalName: 'foundit',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'foundit',
      adapterName: 'foundit',
      containerSelector: '#applyForm, .apply-drawer, form',
    });
  },
};

