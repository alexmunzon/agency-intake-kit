"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

// Only the page you are on is marked current, for screen readers and by style.
export function NavLink({ href, label }: { href: string; label: string }) {
  const current = usePathname() === href;
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "block rounded-md px-3 py-1.5 font-medium focus-visible:outline-2 focus-visible:outline-indigo-600",
        current ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300" : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
      )}
    >
      {label}
    </Link>
  );
}
