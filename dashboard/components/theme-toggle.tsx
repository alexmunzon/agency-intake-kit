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
      className="theme-toggle"
    >
      <Moon aria-hidden className="size-3.5" />
      Dark mode
    </button>
  );
}
