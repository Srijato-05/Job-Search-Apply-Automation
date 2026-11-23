import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const indeedAdapter: PortalAdapter = {
  name: 'indeed',
  portalName: 'indeed',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'indeed',
      adapterName: 'indeed',
      containerSelector: '#ia-container, .ia-BasePage-content, form',
    });
  },
};

