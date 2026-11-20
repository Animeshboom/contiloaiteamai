/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public API origin for hosted builds; empty = same-origin /api (dev proxy, Docker nginx). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
