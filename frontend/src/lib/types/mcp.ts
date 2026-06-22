export type MCPTransport = 'stdio' | 'http' | 'sse' | 'websocket'
export type MCPToolPermission = 'read' | 'mutate' | 'disabled'

export interface MCPServer {
  id?: string | null
  name: string
  transport: MCPTransport
  command?: string | null
  args: string[]
  env: Record<string, string>
  env_keys: string[]
  url?: string | null
  auth_env_var?: string | null
  enabled: boolean
  allowed_tools: string[]
  disabled_tools: string[]
  tool_permissions: Record<string, MCPToolPermission>
  timeout: number
  concurrency: number
  metadata: Record<string, unknown>
}

export interface MCPServerInput {
  name: string
  transport: MCPTransport
  command?: string | null
  args?: string[]
  env?: Record<string, string>
  url?: string | null
  auth_env_var?: string | null
  enabled?: boolean
  allowed_tools?: string[]
  disabled_tools?: string[]
  tool_permissions?: Record<string, MCPToolPermission>
  timeout?: number
  concurrency?: number
  metadata?: Record<string, unknown>
}

export interface MCPTool {
  name: string
  description?: string | null
  input_schema: Record<string, unknown>
  enabled: boolean
  permission: MCPToolPermission
}

export interface MCPServerTestResult {
  success: boolean
  message: string
  tools: MCPTool[]
}

export interface MCPToolCallInput {
  server_id: string
  tool_name: string
  arguments?: Record<string, unknown>
  allow_mutation?: boolean
}

export interface MCPToolCallResult {
  success: boolean
  message: string
  tool_name: string
  permission: MCPToolPermission
  is_error: boolean
  content: Array<Record<string, unknown>>
  text: string
  truncated: boolean
}
