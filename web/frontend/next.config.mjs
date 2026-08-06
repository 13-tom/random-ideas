/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    // Clip thumbnails/previews are short-lived presigned R2 URLs on an
    // arbitrary bucket domain, so we don't run them through next/image's
    // optimizer (would need a fixed allow-listed host + adds a serverless
    // function on every image on the free tier). Plain <img>/<video> tags
    // are used instead where those URLs are rendered.
    unoptimized: true,
  },
};

export default nextConfig;
