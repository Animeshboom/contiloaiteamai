/* Runs before the app loads so the page never flashes the wrong theme. Kept as a file (not inline)
 * because the Content-Security-Policy only allows scripts from 'self'. Same rules as src/lib/theme.ts. */
(function () {
  var saved = null
  try { saved = localStorage.getItem("studiotrack.theme") } catch (e) { /* storage blocked */ }
  var dark = saved === "dark" || saved === "light" ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches
  document.documentElement.classList.toggle("dark", dark)
})()
