/** Light / dark theme: the OS preference on first visit, then whatever the person picked (remembered on this device).
 * public/theme-init.js applies the same rule before React loads, so there is no flash of the wrong theme. */
import { useSyncExternalStore } from "react"

export type Theme = "light" | "dark"

export const THEME_KEY = "studiotrack.theme"

function saved(): Theme | null {
  try {
    const v = localStorage.getItem(THEME_KEY)
    return v === "light" || v === "dark" ? v : null
  } catch {
    return null
  }
}

function systemTheme(): Theme {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
  } catch {
    return "light"
  }
}

const listeners = new Set<() => void>()

export function getTheme(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}

export function setTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark")
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
  listeners.forEach((l) => l())
}

/** Make sure <html> matches the saved / OS theme (normally already done by theme-init.js). */
export function initTheme() {
  document.documentElement.classList.toggle("dark", (saved() ?? systemTheme()) === "dark")
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const theme = useSyncExternalStore(subscribe, getTheme, () => "light" as Theme)
  return [theme, setTheme]
}
