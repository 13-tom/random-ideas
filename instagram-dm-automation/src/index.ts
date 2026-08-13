import express from "express";
import path from "path";
import { config } from "./config";
import { instagramWebhookRouter } from "./webhooks/instagramWebhook";
import { keywordRulesRouter } from "./routes/keywordRules";
import { commentRulesRouter } from "./routes/commentRules";
import { welcomeMessageRouter } from "./routes/welcomeMessage";
import { flowsRouter } from "./routes/flows";
import { scheduledPostsRouter } from "./routes/scheduledPosts";
import { messageLogsRouter } from "./routes/messageLogs";
import { startPostingScheduler } from "./posting/scheduler";
import { requireAdminAuth } from "./middleware/basicAuth";

const app = express();

// The webhook route needs the raw body to verify Meta's signature, so it
// gets its own raw parser instead of the JSON parser used everywhere else.
app.use("/webhooks/instagram", express.raw({ type: "application/json" }), instagramWebhookRouter);

app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true }));

// The dashboard and every rule/flow/post management endpoint sit behind the
// same admin credential — they're the same trust boundary.
app.use("/admin", requireAdminAuth, express.static(path.join(__dirname, "../public")));

app.use("/api/keyword-rules", requireAdminAuth, keywordRulesRouter);
app.use("/api/comment-rules", requireAdminAuth, commentRulesRouter);
app.use("/api/welcome-message", requireAdminAuth, welcomeMessageRouter);
app.use("/api/flows", requireAdminAuth, flowsRouter);
app.use("/api/scheduled-posts", requireAdminAuth, scheduledPostsRouter);
app.use("/api/message-logs", requireAdminAuth, messageLogsRouter);

app.listen(config.port, () => {
  console.log(`Instagram DM automation server listening on port ${config.port}`);
});

startPostingScheduler();
