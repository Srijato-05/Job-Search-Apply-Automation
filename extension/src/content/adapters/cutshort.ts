import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const cutshortAdapter: PortalAdapter = {
  name: 'cutshort',
  portalName: 'cutshort',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'cutshort',
      adapterName: 'cutshort',
      containerSelector: '.apply-modal, form',
    });
  },
};

