import { Router } from "express";
import { z } from "zod";
import { db } from "../db";

export const keywordRulesRouter = Router();

const matchTypeSchema = z.enum(["CONTAINS", "EXACT", "STARTS_WITH"]);

const createSchema = z.object({
  keyword: z.string().min(1),
  matchType: matchTypeSchema.default("CONTAINS"),
  replyText: z.string().min(1),
  isActive: z.boolean().default(true),
});

const updateSchema = createSchema.partial();

keywordRulesRouter.get("/", async (_req, res) => {
  res.json(await db.keywordRule.findMany({ orderBy: { createdAt: "desc" } }));
});

keywordRulesRouter.post("/", async (req, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.status(201).json(await db.keywordRule.create({ data: parsed.data }));
});

keywordRulesRouter.patch("/:id", async (req, res) => {
  const parsed = updateSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.json(await db.keywordRule.update({ where: { id: req.params.id }, data: parsed.data }));
});

keywordRulesRouter.delete("/:id", async (req, res) => {
  await db.keywordRule.delete({ where: { id: req.params.id } });
  res.sendStatus(204);
});
