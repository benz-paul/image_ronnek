import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Storytelling Pipeline Player",
  description: "Interactive educational slideshow with audio narration",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#0f0f1a] text-[#e8e8f0]">
        {children}
      </body>
    </html>
  );
}
