import {
  highlightAmberField,
  isSubmitLikeControl,
  setNativeInputValue,
  withAutoSubmitShield,
} from '../dom_engine';
import { isBlockedPiiField } from '../pii_guard';
import { resolveFactAnswer, resolveLearnedQaAnswer, runHeuristicAutofill } from './generic_heuristic';
import type { PortalAdapter } from './types';

export const naukriAdapter: PortalAdapter = {
  name: 'naukri',
  portalName: 'naukri',
  run(ctx) {
    const { document: doc, vault, qaRules } = ctx;
    const report = runHeuristicAutofill(ctx, {
      portalName: 'naukri',
      adapterName: 'naukri',
      containerSelector: '#applyForm, .apply-form, form',
    });

    // Support Naukri interactive Chatbot drawer (.chatbot_Drawer) under the submit shield
    withAutoSubmitShield(doc, () => {
      const drawer = doc.querySelector('.chatbot_Drawer, .chatbot_MessageContainer');
      if (drawer) {
        const botMsgs = Array.from(drawer.querySelectorAll('.botMsg, .botItem, [data-bot-msg]'));
        const lastPrompt = botMsgs.length > 0 ? (botMsgs[botMsgs.length - 1].textContent ?? '').trim() : '';
        const chatInput = drawer.querySelector(
          '.chatbot_InputContainer input, input.chatbot_Input, input[type="text"], textarea',
        ) as HTMLInputElement | HTMLTextAreaElement | null;

        if (lastPrompt && chatInput && !isSubmitLikeControl(chatInput)) {
          if (isBlockedPiiField(lastPrompt)) {
            report.blockedPiiFields.push(lastPrompt);
          } else {
            const answer = resolveFactAnswer(lastPrompt, vault) ?? resolveLearnedQaAnswer(lastPrompt, qaRules);
            if (answer !== null) {
              setNativeInputValue(chatInput, answer);
              report.filledFields.push(lastPrompt);
            } else {
              highlightAmberField(chatInput, lastPrompt);
              report.unknownFields.push({ question: lastPrompt, fieldTag: 'chatbot' });
            }
          }
        }
      }
    });

    return report;
  },
};

