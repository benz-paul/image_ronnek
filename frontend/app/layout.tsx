import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Decoder Academy",
  description: "Immersive AI-powered storytelling learning platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Manrope:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen bg-background text-on-surface font-body selection:bg-primary/30 selection:text-primary">
        {children}
      </body>
    </html>
  );
}
