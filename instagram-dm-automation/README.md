# Instagram DM + Posting Automation

Automates Instagram DMs and post publishing via Meta's official Graph API:

- **Keyword auto-reply** — reply automatically when a DM contains a keyword.
- **Comment-to-DM** — when someone comments a keyword on a post/reel, DM them privately (the classic "comment PRICE below" funnel), with an optional public reply too.
- **Welcome message** — greet anyone who DMs the account for the first time.
- **Simple flows** — multi-step, button-driven (quick reply) conversations triggered by a keyword.
- **Scheduled posting** — schedule feed images, videos, or reels to publish automatically at a given time.

This uses the official Instagram Graph API + webhooks (not browser automation or
scraping), so it won't put the Instagram account at risk of a ban — but it does
require a Meta Developer App and an Instagram **Business or Creator** account.

## 1. One-time Meta setup

1. Convert the Instagram account to a **Business** or **Creator** account (Instagram app → Settings → Account type), and connect it to a Facebook Page.
2. Go to [developers.facebook.com](https://developers.facebook.com/) → **My Apps** → **Create App** → type **Business**.
3. In the app dashboard, add the **Instagram Graph API** product (via "Instagram" / "Webhooks" products depending on Meta's current UI — search "Instagram API setup with Facebook Login for Business").
4. Under **App Settings → Basic**, copy the **App Secret** → `META_APP_SECRET`.
5. Generate a **Page Access Token** for the Facebook Page linked to the IG account, with these scopes at minimum:
   - `instagram_basic`
   - `instagram_manage_messages`
   - `instagram_manage_comments`
   - `instagram_content_publish` (only needed for scheduled posting)
   - `pages_manage_metadata`
   Exchange it for a **long-lived token** (Graph API Explorer → `GET /oauth/access_token?grant_type=fb_exchange_token&...`) and put it in `PAGE_ACCESS_TOKEN`.
6. Find the **Instagram Business Account ID** (`GET /me/accounts` then `GET /{page-id}?fields=instagram_business_account`) → `IG_BUSINESS_ACCOUNT_ID`.
7. Make up a random string for `WEBHOOK_VERIFY_TOKEN` — you'll enter the same value in the Meta dashboard's webhook config.
8. Under **Webhooks**, subscribe the app to the `messages`, `messaging_postbacks`, and `comments` fields, pointing at:
   `https://<your-deployed-url>/webhooks/instagram`
   (Meta will call this URL with a `GET` verification handshake first — the server handles that automatically.)
9. During development, add your own IG account as a **Tester** under **App Roles → Roles** so you can message it before the app goes through App Review (production use with real, non-tester accounts requires Meta's App Review for the `instagram_manage_messages` / `instagram_manage_comments` permissions).

## 2. Local setup

```bash
cd instagram-dm-automation
cp .env.example .env   # fill in the values from step 1
npm install
npm run prisma:migrate # creates the SQLite database + tables
npm run dev
```

The server listens on `PORT` (default `3000`). For Meta to reach your webhook locally, tunnel it (e.g. `ngrok http 3000`) and use the tunnel URL in the webhook config.

## 3. Configuring automations

There's no admin UI yet — manage rules via the REST API (e.g. with `curl`, Postman, or Insomnia):

| Resource | Endpoints |
|---|---|
| Keyword auto-reply | `GET/POST /api/keyword-rules`, `PATCH/DELETE /api/keyword-rules/:id` |
| Comment-to-DM | `GET/POST /api/comment-rules`, `PATCH/DELETE /api/comment-rules/:id` |
| Welcome message | `GET/PUT /api/welcome-message` |
| Flows | `GET/POST /api/flows`, `PATCH/DELETE /api/flows/:id` |
| Scheduled posts | `GET/POST /api/scheduled-posts`, `GET /api/scheduled-posts/:id`, `DELETE /api/scheduled-posts/:id`, `POST /api/scheduled-posts/process-due` |

Example — auto-reply to "price":

```bash
curl -X POST localhost:3000/api/keyword-rules \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"price","matchType":"CONTAINS","replyText":"Our starter plan is $29/mo! Want the full price list?"}'
```

Example — comment "PRICE" on any post → private DM:

```bash
curl -X POST localhost:3000/api/comment-rules \
  -H 'Content-Type: application/json' \
  -d '{"keyword":"price","dmText":"Hey! Here'\''s our price list: ...","publicReplyText":"Sent you a DM! 📩"}'
```

Example — a 2-step flow triggered by "start":

```bash
curl -X POST localhost:3000/api/flows \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Onboarding",
    "triggerKeyword": "start",
    "steps": [
      { "order": 0, "messageText": "Are you new here?", "quickReplies": [{"title":"Yes","payload":"1"},{"title":"No","payload":"2"}] },
      { "order": 1, "messageText": "Welcome! Here'\''s how to get started..." },
      { "order": 2, "messageText": "Welcome back! What do you need help with?" }
    ]
  }'
```

Each quick reply's `payload` is the `order` of the step it should jump to.

Example — schedule a reel to publish in an hour:

```bash
curl -X POST localhost:3000/api/scheduled-posts \
  -H 'Content-Type: application/json' \
  -d '{
    "mediaType": "REELS",
    "mediaUrl": "https://example.com/my-video.mp4",
    "caption": "New drop 🚀 #launch",
    "scheduledFor": "2026-08-13T12:00:00Z"
  }'
```

`mediaUrl` must be a **publicly reachable https URL** — Meta's servers fetch the file directly, so localhost/private URLs won't work (upload to S3, Cloudinary, etc. first). A background scheduler polls once a minute, creates the media container once `scheduledFor` is reached, waits for Meta to finish processing it (required for video/reels, near-instant for images), then publishes it. Check `GET /api/scheduled-posts/:id` for `status` (`PENDING` → `CONTAINER_CREATED` → `PUBLISHED`, or `FAILED` with `errorMessage` set) and `publishedMediaId` once live. Only `PENDING` posts can be cancelled via `DELETE` — once Meta has started processing the container there's no take-back.

Note: Instagram enforces a rolling **~25 posts per 24 hours** limit per account via this API.

## 4. How it works

- `src/webhooks/instagramWebhook.ts` — verifies the webhook handshake and each event's `X-Hub-Signature-256`, then dispatches messaging events and comment changes.
- `src/automation/messageHandler.ts` — priority order per inbound DM: continue an in-progress flow → send welcome (first contact) → start a newly triggered flow → fall back to keyword auto-reply.
- `src/automation/commentHandler.ts` — matches inbound comments against `CommentRule`s and sends a private-reply DM (+ optional public reply).
- `src/automation/flowEngine.ts` — encodes/decodes quick-reply payloads as `FLOW:<flowId>:<stepOrder>` and advances a user's `Conversation.activeFlowId/activeFlowStep`.
- `src/posting/postingService.ts` — each scheduler tick, creates a media container for any `ScheduledPost` whose `scheduledFor` has passed, then publishes any container Meta reports as `FINISHED`. `src/posting/scheduler.ts` runs this once a minute; `POST /api/scheduled-posts/process-due` runs it on demand.
- All rules, flows, conversations, message logs, and scheduled posts live in SQLite via Prisma (`prisma/schema.prisma`). Swap `DATABASE_URL` for a Postgres connection string and re-run `prisma migrate` to move to Postgres later — no code changes needed.

## Roadmap

Not built yet:

- **Admin UI** — everything above is managed via the REST API only (curl/Postman); a simple web dashboard would make rule/flow/post management much friendlier.
- **Stories** — the container→publish flow also supports Stories (`media_type: STORIES`); not wired up yet.
- **Retry/backoff for failed posts** — a `FAILED` scheduled post currently stays failed; a manual re-publish endpoint or automatic retry would help with transient Graph API errors.
