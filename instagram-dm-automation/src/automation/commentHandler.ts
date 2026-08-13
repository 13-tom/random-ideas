import { db } from "../db";
import { sendPrivateReplyToComment, replyToComment } from "../instagram/graphClient";
import { matchesKeyword } from "./matcher";
import type { ChangeEvent } from "../types";

/**
 * Handles an inbound "comments" webhook change: matches the comment text
 * against configured CommentRules and, on a match, sends the commenter a
 * private-reply DM (and optionally a public reply on the comment).
 */
export async function handleCommentEvent(change: ChangeEvent): Promise<void> {
  if (change.field !== "comments") return;

  const { id: commentId, text, media } = change.value;
  if (!text) return;

  const rules = await db.commentRule.findMany({ where: { isActive: true } });
  const matchedRule = rules.find((rule) => {
    if (rule.mediaId && rule.mediaId !== media?.id) return false;
    return matchesKeyword(text, rule.keyword, rule.matchType);
  });

  if (!matchedRule) return;

  await sendPrivateReplyToComment(commentId, matchedRule.dmText);

  if (matchedRule.publicReplyText) {
    await replyToComment(commentId, matchedRule.publicReplyText);
  }
}
