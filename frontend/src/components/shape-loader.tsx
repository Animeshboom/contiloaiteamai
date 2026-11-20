/**
 * Circle / triangle / square loading animation (after a Uiverse.io design by mobinkakei).
 * Styles: `.st-loader*` in index.css (also inlined in index.html for the very first page load).
 */
export function ShapeLoader({ label = "Loading…", fullScreen = false }: { label?: string; fullScreen?: boolean }) {
  return (
    <div role="status" aria-live="polite"
      className={`grid place-items-center ${fullScreen ? "min-h-screen" : "min-h-[50vh]"}`}>
      <div className="flex flex-col items-center gap-4">
        <div className="st-loaders" aria-hidden="true">
          <div className="st-loader">
            <svg viewBox="0 0 80 80"><circle r="32" cy="40" cx="40" /></svg>
          </div>
          <div className="st-loader st-triangle">
            <svg viewBox="0 0 86 80"><polygon points="43 8 79 72 7 72" /></svg>
          </div>
          <div className="st-loader">
            <svg viewBox="0 0 80 80"><rect height="64" width="64" y="8" x="8" /></svg>
          </div>
        </div>
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
    </div>
  )
}
