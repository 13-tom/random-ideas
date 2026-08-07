import type { Metadata, Viewport } from "next";
import { displayFont, sansFont } from "./fonts";
import { AuthProvider } from "@/lib/auth-context";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import "./globals.css";

export const metadata: Metadata = {
  // TODO: swap for the real domain once registered.
  metadataBase: new URL("https://katgaireel.io"),
  title: {
    default: "KatGai Reel — AI clips from your long videos",
    template: "%s · KatGai Reel",
  },
  description:
    "Upload a long video and KatGai Reel finds the best moments, reframes them for vertical/square, and burns in styled captions — automatically.",
  openGraph: {
    title: "KatGai Reel — AI clips from your long videos",
    description:
      "Upload once. Get a feed of ready-to-post short clips, reframed and captioned automatically.",
    siteName: "KatGai Reel",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#08090c",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${displayFont.variable} ${sansFont.variable}`}>
      <body className="flex min-h-screen flex-col bg-ink-950 font-sans">
        <AuthProvider>
          <Navbar />
          <main className="flex-1">{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}
