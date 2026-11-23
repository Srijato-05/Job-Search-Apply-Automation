import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const ashbyAdapter: PortalAdapter = {
  name: 'ashby',
  portalName: 'ashby',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'ashby',
      adapterName: 'ashby',
      containerSelector: '.ashby-job-posting-form, form',
    });
  },
};

