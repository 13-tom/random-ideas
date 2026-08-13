import axios from "axios";
import { config } from "../config";

const client = axios.create({
  baseURL: config.graphApiBaseUrl,
  params: { access_token: config.pageAccessToken },
});

export interface QuickReply {
  title: string;
  payload: string;
}

/** Send a plain text DM to an Instagram-scoped user id. */
export async function sendTextMessage(igUserId: string, text: string): Promise<void> {
  await client.post(`/${config.igBusinessAccountId}/messages`, {
    recipient: { id: igUserId },
    message: { text },
  });
}

/** Send a DM with quick-reply buttons, used to drive multi-step flows. */
export async function sendQuickReplies(
  igUserId: string,
  text: string,
  quickReplies: QuickReply[]
): Promise<void> {
  await client.post(`/${config.igBusinessAccountId}/messages`, {
    recipient: { id: igUserId },
    message: {
      text,
      quick_replies: quickReplies.map((qr) => ({
        content_type: "text",
        title: qr.title,
        payload: qr.payload,
      })),
    },
  });
}

/**
 * Send a DM to a user who left a comment, without requiring them to have
 * messaged the account first. Used for the "comment KEYWORD to get a DM" funnel.
 */
export async function sendPrivateReplyToComment(commentId: string, text: string): Promise<void> {
  await client.post(`/${commentId}/private_replies`, { message: text });
}

/** Optionally reply publicly to the triggering comment as well. */
export async function replyToComment(commentId: string, text: string): Promise<void> {
  await client.post(`/${commentId}/replies`, { message: text });
}
