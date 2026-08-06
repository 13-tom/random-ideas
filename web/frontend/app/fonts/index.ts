import localFont from "next/font/local";

// Self-hosted (no network fetch at build time — important for a
// cost/robustness-constrained free-tier deploy). Outfit for display/headline
// type, Work Sans for body/UI text. Both OFL-licensed, license files sit
// alongside the .ttf sources in this folder.

export const displayFont = localFont({
  src: [
    { path: "./Outfit-Regular.ttf", weight: "400", style: "normal" },
    { path: "./Outfit-Bold.ttf", weight: "700", style: "normal" },
  ],
  variable: "--font-display",
  display: "swap",
});

export const sansFont = localFont({
  src: [
    { path: "./WorkSans-Regular.ttf", weight: "400", style: "normal" },
    { path: "./WorkSans-Italic.ttf", weight: "400", style: "italic" },
    { path: "./WorkSans-Bold.ttf", weight: "700", style: "normal" },
    { path: "./WorkSans-BoldItalic.ttf", weight: "700", style: "italic" },
  ],
  variable: "--font-sans",
  display: "swap",
});
