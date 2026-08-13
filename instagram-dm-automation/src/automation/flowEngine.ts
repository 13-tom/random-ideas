import { db } from "../db";
import { sendQuickReplies, sendTextMessage, QuickReply } from "../instagram/graphClient";
import { matchesKeyword } from "./matcher";

const FLOW_PAYLOAD_PREFIX = "FLOW";

export function encodeFlowPayload(flowId: string, stepOrder: number): string {
  return `${FLOW_PAYLOAD_PREFIX}:${flowId}:${stepOrder}`;
}

export function decodeFlowPayload(payload: string): { flowId: string; stepOrder: number } | null {
  const parts = payload.split(":");
  if (parts.length !== 3 || parts[0] !== FLOW_PAYLOAD_PREFIX) return null;
  const stepOrder = Number(parts[2]);
  if (Number.isNaN(stepOrder)) return null;
  return { flowId: parts[1], stepOrder };
}

function parseQuickReplies(json: string | null): QuickReply[] | undefined {
  if (!json) return undefined;
  try {
    return JSON.parse(json) as QuickReply[];
  } catch {
    return undefined;
  }
}

async function sendStep(
  igUserId: string,
  flowId: string,
  step: { order: number; messageText: string; quickReplies: string | null }
): Promise<void> {
  const quickReplies = parseQuickReplies(step.quickReplies);
  if (quickReplies?.length) {
    // Each quick reply's stored `payload` is the order of the step it leads to.
    // Rewrite it into a FLOW:<flowId>:<nextOrder> payload the webhook can decode.
    const rewritten = quickReplies.map((qr) => ({
      title: qr.title,
      payload: encodeFlowPayload(flowId, Number(qr.payload)),
    }));
    await sendQuickReplies(igUserId, step.messageText, rewritten);
  } else {
    await sendTextMessage(igUserId, step.messageText);
  }
}

/** Starts a flow for a user: sends step 0 and marks it active on their conversation. */
export async function startFlow(igUserId: string, flowId: string): Promise<void> {
  const firstStep = await db.flowStep.findUnique({
    where: { flowId_order: { flowId, order: 0 } },
  });
  if (!firstStep) return;

  await db.conversation.update({
    where: { igUserId },
    data: { activeFlowId: flowId, activeFlowStep: 0 },
  });

  await sendStep(igUserId, flowId, firstStep);
}

/**
 * Advances a user's active flow based on the payload from the quick reply
 * they tapped. Clears the active flow once the last step has been sent.
 */
export async function advanceFlow(igUserId: string, payload: string): Promise<boolean> {
  const decoded = decodeFlowPayload(payload);
  if (!decoded) return false;

  const nextStep = await db.flowStep.findUnique({
    where: { flowId_order: { flowId: decoded.flowId, order: decoded.stepOrder } },
  });

  if (!nextStep) {
    await db.conversation.update({
      where: { igUserId },
      data: { activeFlowId: null, activeFlowStep: null },
    });
    return true;
  }

  // A step with no quick replies has nothing left to advance to, so it ends the flow.
  const isTerminalStep = !parseQuickReplies(nextStep.quickReplies)?.length;

  await db.conversation.update({
    where: { igUserId },
    data: {
      activeFlowId: isTerminalStep ? null : decoded.flowId,
      activeFlowStep: isTerminalStep ? null : decoded.stepOrder,
    },
  });

  await sendStep(igUserId, decoded.flowId, nextStep);
  return true;
}

/** Finds the first active flow whose trigger keyword matches inbound text. */
export async function findTriggeredFlow(text: string) {
  const flows = await db.flow.findMany({ where: { isActive: true } });
  return flows.find((flow) => matchesKeyword(text, flow.triggerKeyword, flow.triggerMatch)) ?? null;
}
