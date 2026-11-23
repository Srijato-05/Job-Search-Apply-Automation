import { ashbyAdapter } from './ashby';
import { cutshortAdapter } from './cutshort';
import { founditAdapter } from './foundit';
import { genericHeuristicAdapter } from './generic_heuristic';
import { greenhouseAdapter } from './greenhouse';
import { hiristAdapter } from './hirist';
import { indeedAdapter } from './indeed';
import { instahyreAdapter } from './instahyre';
import { leverAdapter } from './lever';
import { linkedinAdapter } from './linkedin';
import { naukriAdapter } from './naukri';
import { smartrecruitersAdapter } from './smartrecruiters';
import type { PortalAdapter } from './types';
import { workdayAdapter } from './workday';

const ADAPTERS: Record<string, PortalAdapter> = {
  greenhouse: greenhouseAdapter,
  lever: leverAdapter,
  ashby: ashbyAdapter,
  smartrecruiters: smartrecruitersAdapter,
  workday: workdayAdapter,
  naukri: naukriAdapter,
  linkedin: linkedinAdapter,
  indeed: indeedAdapter,
  instahyre: instahyreAdapter,
  foundit: founditAdapter,
  hirist: hiristAdapter,
  cutshort: cutshortAdapter,
  generic: genericHeuristicAdapter,
};

export function getAdapterForPortal(portalName: string): PortalAdapter {
  return ADAPTERS[portalName.toLowerCase()] ?? genericHeuristicAdapter;
}

export const ALL_ADAPTER_NAMES = Object.keys(ADAPTERS);

