import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const instahyreAdapter: PortalAdapter = {
  name: 'instahyre',
  portalName: 'instahyre',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'instahyre',
      adapterName: 'instahyre',
      containerSelector: '#candidate-apply-form, .apply-modal, form',
    });
  },
};

