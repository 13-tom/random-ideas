import { db } from "../db";
import {
  createMediaContainer,
  getContainerStatus,
  publishMediaContainer,
  MediaContainerType,
} from "../instagram/graphClient";

async function markFailed(id: string, err: unknown): Promise<void> {
  const message = err instanceof Error ? err.message : String(err);
  await db.scheduledPost.update({
    where: { id },
    data: { status: "FAILED", errorMessage: message },
  });
}

async function createContainersForDuePosts(): Promise<void> {
  const due = await db.scheduledPost.findMany({
    where: { status: "PENDING", scheduledFor: { lte: new Date() } },
  });

  for (const post of due) {
    try {
      const containerId = await createMediaContainer({
        mediaType: post.mediaType as MediaContainerType,
        mediaUrl: post.mediaUrl,
        caption: post.caption ?? undefined,
      });
      await db.scheduledPost.update({
        where: { id: post.id },
        data: { status: "CONTAINER_CREATED", containerId },
      });
    } catch (err) {
      await markFailed(post.id, err);
    }
  }
}

async function publishReadyContainers(): Promise<void> {
  const processing = await db.scheduledPost.findMany({
    where: { status: "CONTAINER_CREATED" },
  });

  for (const post of processing) {
    if (!post.containerId) continue;

    try {
      const status = await getContainerStatus(post.containerId);

      if (status === "FINISHED") {
        const publishedMediaId = await publishMediaContainer(post.containerId);
        await db.scheduledPost.update({
          where: { id: post.id },
          data: { status: "PUBLISHED", publishedMediaId },
        });
      } else if (status === "ERROR" || status === "EXPIRED") {
        await markFailed(post.id, new Error(`Media container ${post.containerId} status: ${status}`));
      }
      // IN_PROGRESS (video/reel still processing on Meta's side): check again next tick.
    } catch (err) {
      await markFailed(post.id, err);
    }
  }
}

/** One scheduler tick: create containers for anything now due, then publish anything ready. */
export async function processDuePosts(): Promise<void> {
  await createContainersForDuePosts();
  await publishReadyContainers();
}
