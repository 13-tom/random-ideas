import "dotenv/config";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const config = {
  port: Number(process.env.PORT ?? 3000),
  metaAppSecret: requireEnv("META_APP_SECRET"),
  webhookVerifyToken: requireEnv("WEBHOOK_VERIFY_TOKEN"),
  pageAccessToken: requireEnv("PAGE_ACCESS_TOKEN"),
  igBusinessAccountId: requireEnv("IG_BUSINESS_ACCOUNT_ID"),
  graphApiBaseUrl: "https://graph.facebook.com/v20.0",
};
