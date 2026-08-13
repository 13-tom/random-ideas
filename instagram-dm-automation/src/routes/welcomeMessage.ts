import { Router } from "express";
import { z } from "zod";
import { db } from "../db";

export const welcomeMessageRouter = Router();

const upsertSchema = z.object({
  text: z.string().min(1),
  isActive: z.boolean().default(true),
});

// Single-record resource: there's one active welcome message at a time.
welcomeMessageRouter.get("/", async (_req, res) => {
  res.json(await db.welcomeMessage.findFirst({ orderBy: { updatedAt: "desc" } }));
});

welcomeMessageRouter.put("/", async (req, res) => {
  const parsed = upsertSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }

  const existing = await db.welcomeMessage.findFirst();
  const saved = existing
    ? await db.welcomeMessage.update({ where: { id: existing.id }, data: parsed.data })
    : await db.welcomeMessage.create({ data: parsed.data });

  res.json(saved);
});
