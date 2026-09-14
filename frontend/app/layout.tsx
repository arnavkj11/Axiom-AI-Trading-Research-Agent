import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans, Newsreader } from "next/font/google";
import Link from "next/link";
import "./globals.css";

// Newsreader carries the verdicts and thesis prose — research notes are
// editorial documents, and this is the product's voice.
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
});

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

// Mono is for numerals only, where tabular alignment does real work.
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Axiom — AI Equity Research",
  description:
    "Two analysts argue, a judge rules, and every claim cites its evidence.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${newsreader.variable} ${plexSans.variable} ${plexMono.variable} h-full`}
    >
      <body className="flex min-h-full flex-col">
        <header className="border-b border-line-soft">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="group flex items-baseline gap-2.5">
              <span className="font-display text-lg tracking-tight text-fg">
                Axiom
              </span>
              <span className="h-3 w-px bg-line" aria-hidden />
              <span className="text-xs text-faint transition-colors group-hover:text-muted">
                equity research
              </span>
            </Link>
          </div>
        </header>

        <div className="flex-1">{children}</div>

        <footer className="border-t border-line-soft">
          <div className="mx-auto max-w-5xl px-6 py-5 text-xs leading-relaxed text-faint">
            Research output, not investment advice. Verdicts are unvalidated —
            no backtesting yet — and conviction scores are not calibrated
            probabilities.
          </div>
        </footer>
      </body>
    </html>
  );
}
