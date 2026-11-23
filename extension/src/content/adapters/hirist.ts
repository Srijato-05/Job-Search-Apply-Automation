import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const hiristAdapter: PortalAdapter = {
  name: 'hirist',
  portalName: 'hirist',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'hirist',
      adapterName: 'hirist',
      containerSelector: '.apply-form, form',
    });
  },
};

