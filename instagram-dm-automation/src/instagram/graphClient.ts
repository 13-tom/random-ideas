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

export type MediaContainerType = "IMAGE" | "REELS" | "VIDEO";
export type ContainerStatus = "EXPIRED" | "ERROR" | "FINISHED" | "IN_PROGRESS" | "PUBLISHED";

/**
 * Step 1 of publishing: create a media container from a publicly reachable
 * image/video URL. Video containers process asynchronously on Meta's side —
 * poll getContainerStatus() until it's FINISHED before publishing.
 */
export async function createMediaContainer(params: {
  mediaType: MediaContainerType;
  mediaUrl: string;
  caption?: string;
}): Promise<string> {
  const { mediaType, mediaUrl, caption } = params;
  const body: Record<string, unknown> = { caption };

  if (mediaType === "IMAGE") {
    body.image_url = mediaUrl;
  } else {
    body.video_url = mediaUrl;
    body.media_type = mediaType;
  }

  const { data } = await client.post(`/${config.igBusinessAccountId}/media`, body);
  return data.id as string;
}

/** Checks whether a media container has finished processing and is ready to publish. */
export async function getContainerStatus(containerId: string): Promise<ContainerStatus> {
  const { data } = await client.get(`/${containerId}`, { params: { fields: "status_code" } });
  return data.status_code as ContainerStatus;
}

/** Step 2 of publishing: publish a FINISHED container. Returns the published media id. */
export async function publishMediaContainer(containerId: string): Promise<string> {
  const { data } = await client.post(`/${config.igBusinessAccountId}/media_publish`, {
    creation_id: containerId,
  });
  return data.id as string;
}
