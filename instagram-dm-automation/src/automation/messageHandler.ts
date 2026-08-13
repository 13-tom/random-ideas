import { db } from "../db";
import { sendTextMessage } from "../instagram/graphClient";
import { matchesKeyword } from "./matcher";
import { startFlow, advanceFlow, findTriggeredFlow } from "./flowEngine";
import type { MessagingEvent } from "../types";

async function logMessage(igUserId: string, direction: "inbound" | "outbound", text?: string, meta?: unknown) {
  await db.messageLog.create({
    data: {
      igUserId,
      direction,
      text,
      meta: meta ? JSON.stringify(meta) : null,
    },
  });
}

async function getOrCreateConversation(igUserId: string) {
  return db.conversation.upsert({
    where: { igUserId },
    update: { lastInteractionAt: new Date() },
    create: { igUserId },
  });
}

async function maybeSendWelcome(igUserId: string, hasReceivedWelcome: boolean): Promise<boolean> {
  if (hasReceivedWelcome) return false;

  const welcome = await db.welcomeMessage.findFirst({ where: { isActive: true } });
  if (!welcome) return false;

  await sendTextMessage(igUserId, welcome.text);
  await logMessage(igUserId, "outbound", welcome.text, { source: "welcome" });
  await db.conversation.update({
    where: { igUserId },
    data: { hasReceivedWelcome: true },
  });
  return true;
}

/**
 * Handles one inbound DM/postback event: logs it, sends a welcome message on
 * first contact, advances an in-progress flow, starts a newly triggered flow,
 * or falls back to a plain keyword auto-reply — in that priority order.
 */
export async function handleMessagingEvent(event: MessagingEvent): Promise<void> {
  const igUserId = event.sender.id;
  const text = event.message?.text;
  const quickReplyPayload = event.message?.quick_reply?.payload ?? event.postback?.payload;

  await logMessage(igUserId, "inbound", text, { quickReplyPayload });

  const conversation = await getOrCreateConversation(igUserId);

  if (quickReplyPayload) {
    const advanced = await advanceFlow(igUserId, quickReplyPayload);
    if (advanced) return;
  }

  await maybeSendWelcome(igUserId, conversation.hasReceivedWelcome);

  if (!text) return;

  if (conversation.activeFlowId) {
    // Mid-flow but the user typed free text instead of tapping a button; ignore
    // rather than derailing the flow. They can still tap a quick reply to continue.
    return;
  }

  const triggeredFlow = await findTriggeredFlow(text);
  if (triggeredFlow) {
    await startFlow(igUserId, triggeredFlow.id);
    return;
  }

  const keywordRules = await db.keywordRule.findMany({ where: { isActive: true } });
  const matchedRule = keywordRules.find((rule) => matchesKeyword(text, rule.keyword, rule.matchType));
  if (matchedRule) {
    await sendTextMessage(igUserId, matchedRule.replyText);
    await logMessage(igUserId, "outbound", matchedRule.replyText, { source: "keyword_rule", ruleId: matchedRule.id });
  }
}
