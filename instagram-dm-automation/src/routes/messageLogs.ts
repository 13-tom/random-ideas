import { Router } from "express";
import { db } from "../db";

export const messageLogsRouter = Router();

messageLogsRouter.get("/", async (req, res) => {
  const igUserId = typeof req.query.igUserId === "string" ? req.query.igUserId : undefined;
  const limit = Math.min(Number(req.query.limit) || 200, 500);

  res.json(
    await db.messageLog.findMany({
      where: igUserId ? { igUserId } : undefined,
      orderBy: { createdAt: "desc" },
      take: limit,
    })
  );
});
