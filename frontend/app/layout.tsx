import type { Metadata } from "next";
import { JetBrains_Mono, Plus_Jakarta_Sans } from "next/font/google";
import { Nav } from "@/components/nav";
import { SelectionProvider } from "@/components/selection";
import "./globals.css";

const sans = Plus_Jakarta_Sans({ subsets: ["latin"], variable: "--font-sans" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono" });

export const metadata: Metadata = {
  title: "Risk Copilot",
  description: "Daily VaR, Expected Shortfall, backtests and limits for a sample multi-asset portfolio.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`}>
      <body className="min-h-screen font-sans">
        <SelectionProvider>
          <Nav />
          <main className="mx-auto flex max-w-[1360px] flex-col gap-5 px-4 pb-16 pt-7 sm:px-6">{children}</main>
          <footer className="mx-auto max-w-[1360px] px-4 pb-10 text-xs text-ink-muted sm:px-6">
            Educational project on public data. Not investment advice. Not affiliated with any employer.
          </footer>
        </SelectionProvider>
      </body>
    </html>
  );
}
