import { Router } from "express";
import { z } from "zod";
import { db } from "../db";
import { processDuePosts } from "../posting/postingService";

export const scheduledPostsRouter = Router();

const mediaTypeSchema = z.enum(["IMAGE", "REELS", "VIDEO"]);

const createSchema = z.object({
  mediaType: mediaTypeSchema,
  mediaUrl: z.string().url(),
  caption: z.string().optional(),
  scheduledFor: z.coerce.date(),
});

scheduledPostsRouter.get("/", async (_req, res) => {
  res.json(await db.scheduledPost.findMany({ orderBy: { scheduledFor: "asc" } }));
});

scheduledPostsRouter.get("/:id", async (req, res) => {
  const post = await db.scheduledPost.findUnique({ where: { id: req.params.id } });
  if (!post) {
    res.sendStatus(404);
    return;
  }
  res.json(post);
});

scheduledPostsRouter.post("/", async (req, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.status(201).json(await db.scheduledPost.create({ data: parsed.data }));
});

// Only PENDING posts can be cancelled — once a container has been created on
// Meta's side, there's no take-back, so let it run its course instead.
scheduledPostsRouter.delete("/:id", async (req, res) => {
  const post = await db.scheduledPost.findUnique({ where: { id: req.params.id } });
  if (!post) {
    res.sendStatus(404);
    return;
  }
  if (post.status !== "PENDING") {
    res.status(409).json({ error: "Only pending (not-yet-started) posts can be cancelled" });
    return;
  }
  await db.scheduledPost.delete({ where: { id: req.params.id } });
  res.sendStatus(204);
});

// Runs a scheduler tick immediately instead of waiting for the next poll interval.
scheduledPostsRouter.post("/process-due", async (_req, res) => {
  await processDuePosts();
  res.sendStatus(202);
});
