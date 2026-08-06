import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Ink: near-black backgrounds for a focused, cinematic dark UI —
        // this is a video tool, footage should be the brightest thing on
        // screen, not chrome around it.
        ink: {
          950: "#08090c",
          900: "#0d0f14",
          850: "#12151c",
          800: "#181c25",
          700: "#232733",
          600: "#343a48",
          500: "#4c5262",
          400: "#6b7180",
          300: "#9298a6",
          200: "#c1c5cf",
          100: "#e4e6ea",
          50: "#f6f7f8",
        },
        // Signal: warm coral/orange accent — stands for the AI "cut" /
        // highlight moment, distinct from the cool violet a lot of AI
        // tools default to.
        signal: {
          400: "#ff8a5c",
          500: "#ff6a3d",
          600: "#f04f24",
          700: "#c93c17",
        },
        // Aux: cool cyan used sparingly for secondary accents/links.
        aux: {
          400: "#5ee8d5",
          500: "#2fd3bd",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "sans-serif",
        ],
        display: ["var(--font-display)", "var(--font-sans)", "sans-serif"],
      },
      backgroundImage: {
        "grid-fade":
          "linear-gradient(to bottom, transparent, rgb(8 9 12))",
        "signal-glow":
          "radial-gradient(60% 60% at 50% 0%, rgba(255,106,61,0.25) 0%, rgba(255,106,61,0) 70%)",
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(255,106,61,0.4), 0 0 24px rgba(255,106,61,0.35)",
      },
      animation: {
        "fade-up": "fade-up 0.6s ease-out both",
        shimmer: "shimmer 2s linear infinite",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
