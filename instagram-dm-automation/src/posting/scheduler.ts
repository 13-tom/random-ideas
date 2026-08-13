import { processDuePosts } from "./postingService";

const POLL_INTERVAL_MS = 60_000;

/** Polls for due/in-progress scheduled posts once a minute. */
export function startPostingScheduler(): NodeJS.Timeout {
  return setInterval(() => {
    processDuePosts().catch((err) => console.error("Posting scheduler tick failed:", err));
  }, POLL_INTERVAL_MS);
}
