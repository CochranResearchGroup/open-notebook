export interface Model {
  id: string
  name: string
  provider: string
  type: 'language' | 'embedding' | 'text_to_speech' | 'speech_to_text'
  credential?: string | null
  created: string
  updated: string
}

export interface CreateModelRequest {
  name: string
  provider: string
  type: 'language' | 'embedding' | 'text_to_speech' | 'speech_to_text'
  credential?: string
}

export interface ModelDefaults {
  default_chat_model?: string | null
  default_transformation_model?: string | null
  large_context_model?: string | null
  default_text_to_speech_model?: string | null
  default_speech_to_text_model?: string | null
  default_embedding_model?: string | null
  default_tools_model?: string | null
}

export interface ProviderAvailability {
  available: string[]
  unavailable: string[]
  supported_types: Record<string, string[]>
}

// Model Discovery Types
export interface DiscoveredModel {
  name: string
  provider: string
  model_type: 'language' | 'embedding' | 'text_to_speech' | 'speech_to_text'
  description?: string
}

export interface ProviderSyncResult {
  provider: string
  discovered: number
  new: number
  existing: number
}

export interface AllProvidersSyncResult {
  results: Record<string, ProviderSyncResult>
  total_discovered: number
  total_new: number
}

export interface ProviderModelCount {
  provider: string
  counts: Record<string, number>
  total: number
}

export interface AutoAssignResult {
  assigned: Record<string, string>  // slot_name -> model_id
  skipped: string[]  // slots already assigned
  missing: string[]  // slots with no available models
}

export interface ModelTestResult {
  success: boolean
  message: string
  details?: string
}

export interface CodexAppServerStatus {
  provider: string
  enabled: boolean
  available: boolean
  cli_found: boolean
  help_ok: boolean
  help_error?: string | null
  codex_bin: string
  codex_bin_path?: string | null
  profile: string
  codex_home_configured: boolean
  codex_home_label?: string | null
  model: string
  cwd: string
  effort: string
  sandbox: string
  timeout: number
  registered_model_id?: string | null
  default_slots: Record<string, boolean>
}

export interface CodexAppServerDefaults {
  model_id: string
  default_chat_model: string
  default_transformation_model: string
  large_context_model: string
  default_tools_model: string
}

export type CodexMCPProfileMode = 'none' | 'read_only' | 'selected' | 'custom'

export interface CodexMCPServerSummary {
  id?: string | null
  name: string
  transport: string
  enabled: boolean
  codex_native_supported: boolean
  has_mutating_classification: boolean
  env_keys: string[]
}

export interface CodexMCPProfile {
  mode: CodexMCPProfileMode
  selected_server_ids: string[]
  custom_profile_name?: string | null
  available_servers: CodexMCPServerSummary[]
  codex_config_toml: string
  warnings: string[]
}

export interface CodexMCPProfileUpdate {
  mode: CodexMCPProfileMode
  selected_server_ids: string[]
  custom_profile_name?: string | null
}
