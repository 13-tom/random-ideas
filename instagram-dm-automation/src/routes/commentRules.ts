import { Router } from "express";
import { z } from "zod";
import { db } from "../db";

export const commentRulesRouter = Router();

const matchTypeSchema = z.enum(["CONTAINS", "EXACT", "STARTS_WITH"]);

const createSchema = z.object({
  mediaId: z.string().min(1).optional(),
  keyword: z.string().min(1),
  matchType: matchTypeSchema.default("CONTAINS"),
  dmText: z.string().min(1),
  publicReplyText: z.string().min(1).optional(),
  isActive: z.boolean().default(true),
});

const updateSchema = createSchema.partial();

commentRulesRouter.get("/", async (_req, res) => {
  res.json(await db.commentRule.findMany({ orderBy: { createdAt: "desc" } }));
});

commentRulesRouter.post("/", async (req, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.status(201).json(await db.commentRule.create({ data: parsed.data }));
});

commentRulesRouter.patch("/:id", async (req, res) => {
  const parsed = updateSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.json(await db.commentRule.update({ where: { id: req.params.id }, data: parsed.data }));
});

commentRulesRouter.delete("/:id", async (req, res) => {
  await db.commentRule.delete({ where: { id: req.params.id } });
  res.sendStatus(204);
});
