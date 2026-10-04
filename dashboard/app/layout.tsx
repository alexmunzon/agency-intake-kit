import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { NavLink } from "@/components/nav-link";
import "./globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Agency Intake Kit",
  description:
    "Can this agency go live? Validation, tie-out, and readiness checks for a newly acquired insurance agency's book of business. Synthetic data only.",
};

// Pages arrive one PR at a time. Unbuilt pages show as disabled items, not broken links.
const PAGES: { label: string; href?: string }[] = [
  { label: "Overview", href: "/" },
  { label: "Sources", href: "/sources" },
  { label: "Exceptions", href: "/exceptions" },
  { label: "Tie-out", href: "/tie-out" },
  { label: "Agents", href: "/agents" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col bg-slate-50 text-slate-900 lg:flex-row dark:bg-slate-950 dark:text-slate-100">
        <nav aria-label="Main" className="border-b border-slate-200 bg-white lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0 dark:border-slate-800 dark:bg-slate-900">
          <p className="px-4 pt-3 pb-2 text-sm font-semibold lg:px-5 lg:pt-6">Agency Intake Kit</p>
          <ul className="flex gap-1 overflow-x-auto px-2 pb-2 text-sm lg:flex-col lg:px-3">
            {PAGES.map(({ label, href }) => (
              <li key={label} className="shrink-0">
                {href ? (
                  <NavLink href={href} label={label} />
                ) : (
                  <span aria-disabled="true" className="block px-3 py-1.5 text-slate-600 dark:text-slate-400">
                    {label} <span className="text-xs">(soon)</span>
                  </span>
                )}
              </li>
            ))}
          </ul>
        </nav>
        <main className="mx-auto w-full max-w-[1120px] px-4 py-6 sm:px-10">{children}</main>
      </body>
    </html>
  );
}
