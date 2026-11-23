import { getAdapterForPortal } from './adapters';
import { detectPortalFromUrl, extractCurrentPageContext, harvestVisibleJobs } from './harvester';
import {
  attachSubmitWatcher,
  detectConfirmationScreen,
  detectExpiredPosting,
  detectNativeAppliedBadge,
} from './submit_watcher';

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'GET_PAGE_CONTEXT') {
    const context = extractCurrentPageContext(document, window.location.href);
    sendResponse({
      ok: true,
      context,
      signals: {
        nativeApplied: detectNativeAppliedBadge(document),
        confirmationSeen: detectConfirmationScreen(document),
        expired: detectExpiredPosting(document),
      },
    });
    return true;
  }

  if (message?.type === 'HARVEST_VISIBLE_JOBS') {
    const jobs = harvestVisibleJobs(document, window.location.href);
    sendResponse({ ok: true, jobs });
    return true;
  }

  if (message?.type === 'RUN_AUTOFILL') {
    const portal = detectPortalFromUrl(window.location.href);
    const adapter = getAdapterForPortal(portal);
    const report = adapter.run({
      document,
      pageUrl: window.location.href,
      vault: message.vault,
      qaRules: message.qaRules ?? [],
      resumePdf: message.resumePdf ?? null,
    });
    sendResponse({ ok: true, report });
    return true;
  }

  return false;
});

attachSubmitWatcher(document, (event) => {
  const context = extractCurrentPageContext(document, window.location.href);
  chrome.runtime.sendMessage({
    type: 'PAGE_LIFECYCLE_EVENT',
    event,
    context,
  });
});

