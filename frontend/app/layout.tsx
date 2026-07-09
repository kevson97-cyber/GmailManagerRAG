import type { Metadata } from "next";
import AppShell from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "GmailManagerRAG",
  description: "Local Gmail sync, search index, and AI assistant control panel.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
