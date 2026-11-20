import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it } from "vitest"

import { initTheme, THEME_KEY } from "@/lib/theme"
import { ThemeToggle } from "./theme-toggle"

describe("ThemeToggle", () => {
  afterEach(() => document.documentElement.classList.remove("dark"))

  it("switches the html dark class and remembers the choice", async () => {
    render(<><ThemeToggle /><ThemeToggle /></>)  // renders more than once: no duplicate ids, both stay in sync
    const [first, second] = screen.getAllByRole("switch", { name: "Dark mode" })
    expect(first).not.toBeChecked()

    await userEvent.click(first)
    expect(document.documentElement).toHaveClass("dark")
    expect(localStorage.getItem(THEME_KEY)).toBe("dark")
    expect(second).toBeChecked()

    second.focus()
    await userEvent.keyboard(" ")  // keyboard works too
    expect(document.documentElement).not.toHaveClass("dark")
    expect(localStorage.getItem(THEME_KEY)).toBe("light")
    expect(first).not.toBeChecked()
  })

  it("restores the saved theme on load", () => {
    localStorage.setItem(THEME_KEY, "dark")
    initTheme()
    expect(document.documentElement).toHaveClass("dark")
  })
})
