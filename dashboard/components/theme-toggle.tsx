"use client";

import { Moon } from "lucide-react";
import { useSyncExternalStore } from "react";

// The inline script in the layout sets the "dark" class before the first paint. This button
// flips it and remembers the choice in localStorage, which can be blocked, so it is optional.
function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

const isDark = () => document.documentElement.classList.contains("dark");

export function ThemeToggle() {
  const dark = useSyncExternalStore(subscribe, isDark, () => false);
  function toggle() {
    document.documentElement.classList.toggle("dark", !dark);
    try {
      localStorage.setItem("theme", dark ? "light" : "dark");
    } catch {
      // Storage blocked: the choice lasts until the page reloads.
    }
  }
  return (
    <button
      type="button"
      aria-pressed={dark}
      onClick={toggle}
      className="flex shrink-0 items-center gap-1.5 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:focus-visible:outline-indigo-400"
    >
      <Moon aria-hidden className="size-3.5" />
      Dark mode
    </button>
  );
}
