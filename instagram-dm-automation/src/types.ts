export interface InstagramWebhookPayload {
  object: string;
  entry: InstagramWebhookEntry[];
}

export interface InstagramWebhookEntry {
  id: string;
  time: number;
  messaging?: MessagingEvent[];
  changes?: ChangeEvent[];
}

export interface MessagingEvent {
  sender: { id: string };
  recipient: { id: string };
  timestamp: number;
  message?: {
    mid: string;
    text?: string;
    quick_reply?: { payload: string };
  };
  postback?: {
    payload: string;
  };
}

export interface ChangeEvent {
  field: string; // e.g. "comments"
  value: {
    id: string; // comment id
    text?: string;
    from?: { id: string; username?: string };
    media?: { id: string; media_product_type?: string };
  };
}
