import { runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const greenhouseAdapter: PortalAdapter = {
  name: 'greenhouse',
  portalName: 'greenhouse',
  run(ctx) {
    return runHeuristicAutofill(ctx, {
      portalName: 'greenhouse',
      adapterName: 'greenhouse',
      containerSelector: '#application_form, form',
      fileInputSelector: '#resume, input[type="file"]',
    });
  },
};

