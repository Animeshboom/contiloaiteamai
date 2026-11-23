import { useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, KeyRound, Sparkles, XCircle } from "lucide-react"
import { toast } from "sonner"

import { LoadingRows } from "@/components/common"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Field, Input } from "@/components/ui/form-controls"
import { api, errorMessage } from "@/lib/api"
import { useAuth } from "@/lib/auth-context"
import { cn } from "@/lib/utils"

interface ProviderInfo {
  provider: string
  label: string
  has_key: boolean
  key_hint: string | null
  model: string | null
  default_model: string | null
  base_url: string | null
  default_base_url: string | null
  is_active: boolean
  updated_at: string | null
}

interface AISettings {
  providers: ProviderInfo[]
  active_provider: string | null
  active_source: "admin" | "env" | null
  env_key_present: boolean
}

interface TestResult { ok: boolean; message: string; model: string | null }

const KEY = ["ai-settings"]

const HELP: Record<string, { keyHint: string; modelHint: string }> = {
  anthropic: { keyHint: "From console.anthropic.com → API Keys (starts with sk-ant-)", modelHint: "Leave empty to use the recommended Claude model" },
  openai: { keyHint: "From platform.openai.com → API keys", modelHint: "The model ID from your OpenAI dashboard" },
  gemini: { keyHint: "From Google AI Studio → Get API key", modelHint: "The Gemini model ID from Google AI Studio" },
  openrouter: { keyHint: "From openrouter.ai → Keys", modelHint: "An OpenRouter model ID, written as provider/model" },
  custom: { keyHint: "Any OpenAI-compatible service (e.g. a local model server)", modelHint: "The model name that service expects" },
}

function ProviderForm({ p, onSaved }: { p: ProviderInfo; onSaved: (s: AISettings) => void }) {
  const [apiKey, setApiKey] = useState("")
  const [model, setModel] = useState(p.model ?? "")
  const [baseUrl, setBaseUrl] = useState(p.base_url ?? "")
  const [busy, setBusy] = useState<"save" | "activate" | "test" | "remove" | "off" | null>(null)
  const [test, setTest] = useState<TestResult | null>(null)
  const needsUrl = p.provider === "custom"
  const showUrl = p.provider !== "anthropic"
  const help = HELP[p.provider]

  useEffect(() => { setModel(p.model ?? ""); setBaseUrl(p.base_url ?? "") }, [p.provider, p.model, p.base_url])

  const run = async <T,>(kind: NonNullable<typeof busy>, fn: () => Promise<T>) => {
    setBusy(kind)
    try { return await fn() } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(null) }
  }

  const save = (makeActive: boolean) => run(makeActive ? "activate" : "save", async () => {
    const res = await api.put<AISettings>(`/admin/ai-settings/${p.provider}`, {
      api_key: apiKey || null, model: model || null, base_url: baseUrl || null, make_active: makeActive,
    })
    setApiKey("")
    onSaved(res)
    toast.success(makeActive ? `${p.label} is now the active AI provider` : `${p.label} settings saved`)
  })

  const doTest = () => run("test", async () => {
    const res = await api.post<TestResult>("/admin/ai-settings/test", {
      provider: p.provider, api_key: apiKey || null, model: model || null, base_url: baseUrl || null,
    })
    setTest(res)
  })

  const removeKey = () => run("remove", async () => {
    onSaved(await api.del<AISettings>(`/admin/ai-settings/${p.provider}/key`))
    toast.success(`${p.label} key removed`)
  })

  const turnOff = () => run("off", async () => {
    onSaved(await api.post<AISettings>(`/admin/ai-settings/${p.provider}/deactivate`))
    toast.success(`${p.label} is no longer active`)
  })

  return (
    <div className="space-y-3">
      <Field label="API key" htmlFor={`key-${p.provider}`}
        hint={p.has_key ? `Saved key ends in …${p.key_hint}. Leave empty to keep it. ${help.keyHint}` : help.keyHint}>
        <Input id={`key-${p.provider}`} type="password" autoComplete="off" value={apiKey}
          onChange={(e) => { setApiKey(e.target.value); setTest(null) }}
          placeholder={p.has_key ? `•••••••• ${p.key_hint}` : "Paste API key"} />
      </Field>
      <Field label="Model" htmlFor={`model-${p.provider}`} hint={help.modelHint}>
        <Input id={`model-${p.provider}`} value={model} onChange={(e) => { setModel(e.target.value); setTest(null) }}
          placeholder={p.default_model ?? "Model ID"} />
      </Field>
      {showUrl && (
        <Field label={needsUrl ? "Base URL" : "Base URL (optional)"} htmlFor={`url-${p.provider}`}
          hint={needsUrl ? "e.g. https://your-server/v1 (http:// only for localhost)" : `Default: ${p.default_base_url}`}>
          <Input id={`url-${p.provider}`} value={baseUrl} onChange={(e) => { setBaseUrl(e.target.value); setTest(null) }}
            placeholder={p.default_base_url ?? "https://…/v1"} />
        </Field>
      )}

      {test && (
        <div className={cn("flex items-center gap-2 rounded-md border p-2 text-xs",
          test.ok ? "border-success/30 bg-success/10 text-success" : "border-destructive/30 bg-destructive/10 text-destructive")}>
          {test.ok ? <CheckCircle2 className="size-4" /> : <XCircle className="size-4" />}
          <span>{test.message}{test.model ? ` · ${test.model}` : ""}</span>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" size="sm" loading={busy === "test"} onClick={doTest}>Test connection</Button>
        <Button type="button" variant="outline" size="sm" loading={busy === "save"} onClick={() => save(false)}>Save</Button>
        {p.is_active ? (
          <Button type="button" variant="outline" size="sm" loading={busy === "off"} onClick={turnOff}>Stop using</Button>
        ) : (
          <Button type="button" size="sm" loading={busy === "activate"} onClick={() => save(true)}>
            <Sparkles />Save &amp; use this provider
          </Button>
        )}
        {p.has_key && (
          <Button type="button" variant="ghost" size="sm" className="text-destructive" loading={busy === "remove"} onClick={removeKey}>
            Remove key
          </Button>
        )}
      </div>
    </div>
  )
}

/** Admin: pick the AI provider used for script breakdowns and EOD report narratives. */
export function AISettingsCard() {
  const qc = useQueryClient()
  const { refreshUser } = useAuth()
  const { data, isLoading } = useQuery({ queryKey: KEY, queryFn: () => api.get<AISettings>("/admin/ai-settings") })
  const [selected, setSelected] = useState<string | null>(null)

  const current = selected ?? data?.providers.find((p) => p.is_active)?.provider ?? data?.providers[0]?.provider
  const p = data?.providers.find((x) => x.provider === current)

  const onSaved = (s: AISettings) => {
    qc.setQueryData(KEY, s)
    void refreshUser().catch(() => undefined) // reload /meta/config so the rest of the app sees the new provider
  }

  const activeLabel = data?.providers.find((x) => x.provider === data.active_provider)?.label

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><KeyRound className="size-4" />AI provider</CardTitle>
        <CardDescription>
          Used for script breakdowns and EOD report narratives. Keys are stored encrypted and never shown again.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading || !data ? <LoadingRows rows={3} /> : (
          <>
            <div className="text-sm">
              {data.active_provider ? (
                <span>
                  Active: <Badge tone="green" dot>{activeLabel}</Badge>
                  {data.active_source === "env" && <span className="ml-2 text-xs text-muted-foreground">(from the server's ANTHROPIC_API_KEY)</span>}
                </span>
              ) : (
                <span className="text-muted-foreground">No AI provider is active. The app uses the basic parser and template reports.</span>
              )}
            </div>
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="AI providers">
              {data.providers.map((x) => (
                <button key={x.provider} type="button" role="tab" aria-selected={x.provider === current}
                  onClick={() => setSelected(x.provider)}
                  className={cn("inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs transition-colors",
                    x.provider === current ? "border-primary bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:bg-muted")}>
                  {x.label}
                  {x.is_active && <span className="size-1.5 rounded-full bg-success" aria-label="active" />}
                  {!x.is_active && x.has_key && <span className="size-1.5 rounded-full bg-muted-foreground" aria-label="key saved" />}
                </button>
              ))}
            </div>
            {p && <ProviderForm key={p.provider} p={p} onSaved={onSaved} />}
          </>
        )}
      </CardContent>
    </Card>
  )
}
