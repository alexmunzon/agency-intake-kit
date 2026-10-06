"use client";

import Link from "next/link";
import { Activity, CircleAlert, ClipboardCheck, Files, Scale, UsersRound } from "lucide-react";
import { usePathname } from "next/navigation";

const ICONS = { "/": ClipboardCheck, "/sources": Files, "/exceptions": CircleAlert, "/tie-out": Scale, "/agents": UsersRound, "/runs": Activity };

// Only the page you are on is highlighted and announced as the current page.
export function NavLink({ href, label }: { href: string; label: string }) {
  const current = usePathname() === href;
  const Icon = ICONS[href as keyof typeof ICONS];
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className="sidebar-link"
    >
      {Icon && <Icon aria-hidden className="size-4" />}
      {label}
    </Link>
  );
}
