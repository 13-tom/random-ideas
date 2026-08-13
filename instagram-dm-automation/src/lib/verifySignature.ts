import crypto from "crypto";
import { config } from "../config";

/**
 * Meta signs each webhook POST body with the app secret. Recompute the
 * signature over the raw body and compare with a timing-safe check to
 * reject forged webhook calls.
 */
export function isValidSignature(rawBody: Buffer, signatureHeader: string | undefined): boolean {
  if (!signatureHeader?.startsWith("sha256=")) {
    return false;
  }

  const expected = crypto
    .createHmac("sha256", config.metaAppSecret)
    .update(rawBody)
    .digest("hex");

  const provided = signatureHeader.slice("sha256=".length);

  const expectedBuf = Buffer.from(expected, "hex");
  const providedBuf = Buffer.from(provided, "hex");

  return expectedBuf.length === providedBuf.length && crypto.timingSafeEqual(expectedBuf, providedBuf);
}
