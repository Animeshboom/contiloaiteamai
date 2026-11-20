/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public API origin for hosted builds; empty = same-origin /api (dev proxy, Docker nginx). */
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SUPABASE_URL?: string
  readonly VITE_SUPABASE_PUBLISHABLE_KEY?: string
  readonly VITE_LOGIN_ID_EMAIL_DOMAIN?: string
  readonly VITE_API_PROXY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
