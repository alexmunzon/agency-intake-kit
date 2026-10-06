import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { LoadedRunBanner, LoadedRunProvider } from "@/components/loaded-run";
import { NavLink } from "@/components/nav-link";
import { ThemeToggle } from "@/components/theme-toggle";
import "./globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Agency Intake Kit",
  description:
    "Can this agency go live? Validation, tie-out, and readiness checks for a newly acquired insurance agency's book of business. Synthetic data only.",
};

const PAGES: { label: string; href: string }[] = [
  { label: "Overview", href: "/" },
  { label: "Sources", href: "/sources" },
  { label: "Exceptions", href: "/exceptions" },
  { label: "Tie-out", href: "/tie-out" },
  { label: "Agents", href: "/agents" },
  { label: "Runs", href: "/runs" },
];

// Runs before the first paint, so a dark page never flashes white. The saved choice wins;
// without one (or with storage blocked) the system setting decides.
const THEME_SCRIPT = `(function(){var d=null;try{var t=localStorage.getItem("theme");if(t==="dark"||t==="light")d=t==="dark"}catch(e){}if(d===null)d=matchMedia("(prefers-color-scheme: dark)").matches;document.documentElement.classList.toggle("dark",d)})()`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${inter.variable} h-full antialiased`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-full flex-col bg-slate-50 text-slate-900 lg:flex-row dark:bg-slate-950 dark:text-slate-100">
        <LoadedRunProvider>
          <nav aria-label="Main" className="border-b border-slate-200 bg-white lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0 dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between gap-2 px-4 pt-3 pb-2 lg:px-5 lg:pt-6">
              <p className="text-sm font-semibold">Agency Intake Kit</p>
              <ThemeToggle />
            </div>
            <ul className="flex gap-1 overflow-x-auto px-2 pb-2 text-sm lg:flex-col lg:px-3">
              {PAGES.map(({ label, href }) => (
                <li key={label} className="shrink-0">
                  <NavLink href={href} label={label} />
                </li>
              ))}
            </ul>
            <section aria-label="Agency Data Trust Series" className="border-t border-slate-200 px-4 py-3 text-xs lg:px-5 dark:border-slate-800">
              <p className="font-semibold">Agency Data Trust Series</p>
              <p className="mt-1 text-slate-600 dark:text-slate-400">Separate demos, shared trust principles.</p>
              <ol className="mt-2 flex flex-wrap gap-x-4 gap-y-2 lg:flex-col">
                <li><span aria-current="page" className="font-medium">1. Intake Kit</span></li>
                <li><a href="https://bob-resolve-nine.vercel.app" className="text-indigo-700 underline dark:text-indigo-300">2. Bob Resolve</a></li>
                <li><a href="https://plan-diff.vercel.app" className="text-indigo-700 underline dark:text-indigo-300">3. Plan Diff</a></li>
              </ol>
            </section>
          </nav>
          <main className="mx-auto w-full max-w-[1120px] min-w-0 px-4 py-6 sm:px-10">
            <LoadedRunBanner />
            {children}
          </main>
        </LoadedRunProvider>
      </body>
    </html>
  );
}
