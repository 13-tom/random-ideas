import { Router } from "express";
import { z } from "zod";
import { db } from "../db";

export const flowsRouter = Router();

const matchTypeSchema = z.enum(["CONTAINS", "EXACT", "STARTS_WITH"]);

const stepSchema = z.object({
  order: z.number().int().min(0),
  messageText: z.string().min(1),
  // Each quick reply's payload is the order of the step it should jump to.
  quickReplies: z.array(z.object({ title: z.string().min(1), payload: z.string().min(1) })).optional(),
});

const createSchema = z.object({
  name: z.string().min(1),
  triggerKeyword: z.string().min(1),
  triggerMatch: matchTypeSchema.default("CONTAINS"),
  isActive: z.boolean().default(true),
  steps: z.array(stepSchema).min(1),
});

flowsRouter.get("/", async (_req, res) => {
  res.json(
    await db.flow.findMany({
      orderBy: { createdAt: "desc" },
      include: { steps: { orderBy: { order: "asc" } } },
    })
  );
});

flowsRouter.post("/", async (req, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }

  const { steps, ...flowData } = parsed.data;
  const flow = await db.flow.create({
    data: {
      ...flowData,
      steps: {
        create: steps.map((step) => ({
          order: step.order,
          messageText: step.messageText,
          quickReplies: step.quickReplies ? JSON.stringify(step.quickReplies) : null,
        })),
      },
    },
    include: { steps: { orderBy: { order: "asc" } } },
  });

  res.status(201).json(flow);
});

flowsRouter.patch("/:id", async (req, res) => {
  const parsed = createSchema.partial().omit({ steps: true }).safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({ error: parsed.error.flatten() });
    return;
  }
  res.json(await db.flow.update({ where: { id: req.params.id }, data: parsed.data }));
});

flowsRouter.delete("/:id", async (req, res) => {
  await db.flow.delete({ where: { id: req.params.id } });
  res.sendStatus(204);
});
