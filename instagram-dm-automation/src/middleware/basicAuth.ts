import crypto from "crypto";
import type { RequestHandler } from "express";

function timingSafeStringEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  // Buffers must be equal length for timingSafeEqual; pad instead of
  // short-circuiting on length so the comparison time doesn't leak it.
  const maxLen = Math.max(bufA.length, bufB.length);
  const paddedA = Buffer.concat([bufA], maxLen);
  const paddedB = Buffer.concat([bufB], maxLen);
  return bufA.length === bufB.length && crypto.timingSafeEqual(paddedA, paddedB);
}

/**
 * Gates the admin dashboard behind HTTP Basic Auth. Fails closed (503) if
 * ADMIN_USERNAME/ADMIN_PASSWORD aren't set, rather than leaving it open.
 *
 * ponytail: single shared admin credential via env var, no per-user accounts
 * or hashed password store. Fine for one operator; move to real auth (hashed
 * passwords, sessions, roles) if more than one person needs access.
 */
export const requireAdminAuth: RequestHandler = (req, res, next) => {
  const expectedUser = process.env.ADMIN_USERNAME;
  const expectedPass = process.env.ADMIN_PASSWORD;

  if (!expectedUser || !expectedPass) {
    res.status(503).send("Admin dashboard is not configured (set ADMIN_USERNAME / ADMIN_PASSWORD).");
    return;
  }

  const header = req.header("authorization");
  const [scheme, encoded] = header?.split(" ") ?? [];

  if (scheme === "Basic" && encoded) {
    const [user, pass] = Buffer.from(encoded, "base64").toString("utf8").split(":");
    if (timingSafeStringEqual(user ?? "", expectedUser) && timingSafeStringEqual(pass ?? "", expectedPass)) {
      next();
      return;
    }
  }

  res.set("WWW-Authenticate", 'Basic realm="Admin Dashboard"');
  res.sendStatus(401);
};
