import { Router } from "express";
import { AxiosError } from "axios";
import { config } from "../config";
import { isValidSignature } from "../lib/verifySignature";
import { handleMessagingEvent } from "../automation/messageHandler";
import { handleCommentEvent } from "../automation/commentHandler";
import type { InstagramWebhookPayload } from "../types";

export const instagramWebhookRouter = Router();

// Meta's one-time handshake when you register/save the webhook URL.
instagramWebhookRouter.get("/", (req, res) => {
  const mode = req.query["hub.mode"];
  const token = req.query["hub.verify_token"];
  const challenge = req.query["hub.challenge"];

  if (mode === "subscribe" && token === config.webhookVerifyToken) {
    res.status(200).send(challenge);
    return;
  }

  res.sendStatus(403);
});

// Real-time events: new DMs, quick-reply taps, postbacks, and comments.
instagramWebhookRouter.post("/", async (req, res) => {
  const rawBody = req.body as Buffer;
  const signature = req.header("x-hub-signature-256");

  if (!isValidSignature(rawBody, signature)) {
    res.sendStatus(401);
    return;
  }

  // Ack immediately — Meta expects a fast 200 and will retry on timeout.
  res.sendStatus(200);

  let payload: InstagramWebhookPayload;
  try {
    payload = JSON.parse(rawBody.toString("utf8"));
  } catch {
    return;
  }

  if (payload.object !== "instagram") return;

  for (const entry of payload.entry) {
    for (const event of entry.messaging ?? []) {
      try {
        await handleMessagingEvent(event);
      } catch (err) {
        console.error("Failed to handle messaging event:", describeError(err));
      }
    }

    for (const change of entry.changes ?? []) {
      try {
        await handleCommentEvent(change);
      } catch (err) {
        console.error("Failed to handle comment event:", describeError(err));
      }
    }
  }
});

function describeError(err: unknown): string {
  if (err instanceof AxiosError) {
    return `Graph API ${err.response?.status ?? "?"}: ${JSON.stringify(err.response?.data ?? err.message)}`;
  }
  return err instanceof Error ? err.message : String(err);
}
