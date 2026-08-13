import express from "express";
import { config } from "./config";
import { instagramWebhookRouter } from "./webhooks/instagramWebhook";
import { keywordRulesRouter } from "./routes/keywordRules";
import { commentRulesRouter } from "./routes/commentRules";
import { welcomeMessageRouter } from "./routes/welcomeMessage";
import { flowsRouter } from "./routes/flows";

const app = express();

// The webhook route needs the raw body to verify Meta's signature, so it
// gets its own raw parser instead of the JSON parser used everywhere else.
app.use("/webhooks/instagram", express.raw({ type: "application/json" }), instagramWebhookRouter);

app.use(express.json());

app.get("/health", (_req, res) => res.json({ ok: true }));

app.use("/api/keyword-rules", keywordRulesRouter);
app.use("/api/comment-rules", commentRulesRouter);
app.use("/api/welcome-message", welcomeMessageRouter);
app.use("/api/flows", flowsRouter);

app.listen(config.port, () => {
  console.log(`Instagram DM automation server listening on port ${config.port}`);
});
