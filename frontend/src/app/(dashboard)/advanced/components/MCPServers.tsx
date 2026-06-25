'use client'

import { useState } from 'react'
import { AlertCircle, CheckCircle2, Download, Loader2, Plug, Trash2 } from 'lucide-react'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import {
  useCreateMCPServer,
  useDeleteMCPServer,
  useDiscoverLocalMCPServers,
  useImportLocalMCPServer,
  useMCPServers,
  useTestMCPServer,
  useUpdateMCPServer,
} from '@/lib/hooks/use-mcp-servers'
import type { MCPServer, MCPServerTestResult } from '@/lib/types/mcp'

function splitArgs(value: string) {
  return value.split('\n').map((item) => item.trim()).filter(Boolean)
}

function parseEnv(value: string) {
  return value.split('\n').reduce<Record<string, string>>((env, line) => {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.includes('=')) return env
    const [key, ...rest] = trimmed.split('=')
    const name = key.trim()
    if (name) env[name] = rest.join('=').trim()
    return env
  }, {})
}

function ServerTools({
  result,
  server,
  onDisableTool,
  onPermissionChange,
}: {
  result?: MCPServerTestResult
  server: MCPServer
  onDisableTool: (toolName: string, disabled: boolean) => void
  onPermissionChange: (toolName: string, permission: 'read' | 'mutate') => void
}) {
  if (!result) return null

  return (
    <div className="space-y-3">
      <Alert variant={result.success ? 'default' : 'destructive'}>
        {result.success ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
        <AlertDescription>{result.message}</AlertDescription>
      </Alert>
      {result.tools.length > 0 && (
        <div className="space-y-2">
          {result.tools.map((tool) => (
            <div key={tool.name} className="rounded-md border p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{tool.name}</span>
                    <Badge variant={tool.enabled ? 'outline' : 'secondary'}>
                      {tool.enabled ? 'enabled' : 'disabled'}
                    </Badge>
                    <Badge variant={tool.permission === 'mutate' ? 'destructive' : 'outline'}>
                      {tool.permission}
                    </Badge>
                  </div>
                  {tool.description && (
                    <p className="text-sm text-muted-foreground">{tool.description}</p>
                  )}
                  {server.id && tool.enabled && tool.permission === 'read' && (
                    <code className="block overflow-x-auto rounded bg-muted px-2 py-1 text-xs">
                      /mcp {server.id} {tool.name} {'{}'}
                    </code>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  <Select
                    value={tool.permission === 'mutate' ? 'mutate' : 'read'}
                    onValueChange={(value) => onPermissionChange(tool.name, value as 'read' | 'mutate')}
                    disabled={!server.id}
                  >
                    <SelectTrigger className="h-9 w-[120px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="read">Read</SelectItem>
                      <SelectItem value="mutate">Mutate</SelectItem>
                    </SelectContent>
                  </Select>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onDisableTool(tool.name, tool.enabled)}
                    disabled={!server.id}
                  >
                    {tool.enabled ? 'Disable' : 'Enable'}
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MCPServerRow({ server }: { server: MCPServer }) {
  const updateServer = useUpdateMCPServer()
  const deleteServer = useDeleteMCPServer()
  const testServer = useTestMCPServer()

  const toggleEnabled = () => {
    if (!server.id) return
    updateServer.mutate({ id: server.id, data: { enabled: !server.enabled } })
  }

  const setToolDisabled = (toolName: string, currentlyEnabled: boolean) => {
    if (!server.id) return
    const disabledTools = currentlyEnabled
      ? Array.from(new Set([...server.disabled_tools, toolName]))
      : server.disabled_tools.filter((name) => name !== toolName)
    updateServer.mutate({ id: server.id, data: { disabled_tools: disabledTools } })
  }

  const setToolPermission = (toolName: string, permission: 'read' | 'mutate') => {
    if (!server.id) return
    updateServer.mutate({
      id: server.id,
      data: {
        tool_permissions: {
          ...server.tool_permissions,
          [toolName]: permission,
        },
      },
    })
  }

  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-medium">{server.name}</h3>
            <Badge variant="outline">{server.transport}</Badge>
            <Badge variant={server.enabled ? 'outline' : 'secondary'}>
              {server.enabled ? 'enabled' : 'disabled'}
            </Badge>
          </div>
          <p className="break-all text-sm text-muted-foreground">
            {server.transport === 'stdio' ? [server.command, ...server.args].filter(Boolean).join(' ') : server.url}
          </p>
          {server.env_keys.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Env keys: {server.env_keys.join(', ')}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => server.id && testServer.mutate(server.id)}
            disabled={!server.id || testServer.isPending}
          >
            {testServer.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plug className="mr-2 h-4 w-4" />}
            Test
          </Button>
          <Button variant="outline" size="sm" onClick={toggleEnabled} disabled={!server.id || updateServer.isPending}>
            {server.enabled ? 'Disable' : 'Enable'}
          </Button>
          <Button
            variant="outline"
            size="icon"
            aria-label={`Delete ${server.name}`}
            onClick={() => server.id && deleteServer.mutate(server.id)}
            disabled={!server.id || deleteServer.isPending}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <ServerTools
        result={testServer.data}
        server={server}
        onDisableTool={setToolDisabled}
        onPermissionChange={setToolPermission}
      />
    </div>
  )
}

function LocalMCPDiscovery() {
  const { data, isLoading, isError, refetch, isFetching } = useDiscoverLocalMCPServers()
  const importServer = useImportLocalMCPServer()
  const candidates = data?.candidates || []

  return (
    <div className="space-y-3 rounded-md border p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="font-medium">Discovered local MCP servers</h3>
          <p className="text-sm text-muted-foreground">
            Import MCP servers found in local agent runtime config. Secret-looking environment values are redacted.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          {isFetching ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Plug className="mr-2 h-4 w-4" />}
          Refresh
        </Button>
      </div>

      {isError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>Could not discover local MCP servers.</AlertDescription>
        </Alert>
      )}

      {data?.warnings?.map((warning) => (
        <Alert key={warning} variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{warning}</AlertDescription>
        </Alert>
      ))}

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Checking local agent config...</div>
      ) : candidates.length === 0 ? (
        <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
          No local MCP servers discovered.
        </div>
      ) : (
        <div className="space-y-2">
          {candidates.map((candidate) => (
            <div key={candidate.candidate_id} className="rounded-md border p-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{candidate.name}</span>
                    <Badge variant="outline">{candidate.source}</Badge>
                    <Badge variant={candidate.already_imported ? 'secondary' : 'outline'}>
                      {candidate.already_imported ? 'imported' : 'available'}
                    </Badge>
                  </div>
                  <p className="break-all text-sm text-muted-foreground">
                    {candidate.transport === 'stdio'
                      ? [candidate.command, ...candidate.args].filter(Boolean).join(' ')
                      : candidate.url}
                  </p>
                  {candidate.env_keys.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Env keys: {candidate.env_keys.join(', ')}
                    </p>
                  )}
                  {candidate.source_path && (
                    <p className="break-all text-xs text-muted-foreground">
                      Source: {candidate.source_path}
                    </p>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => importServer.mutate(candidate.candidate_id)}
                  disabled={candidate.already_imported || importServer.isPending}
                >
                  {importServer.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Download className="mr-2 h-4 w-4" />}
                  Import
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export function MCPServers() {
  const { data: servers = [], isLoading, isError } = useMCPServers()
  const createServer = useCreateMCPServer()
  const [name, setName] = useState('')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [env, setEnv] = useState('')

  const submit = () => {
    createServer.mutate({
      name,
      transport: 'stdio',
      command,
      args: splitArgs(args),
      env: parseEnv(env),
      enabled: true,
      timeout: 30,
      concurrency: 1,
    }, {
      onSuccess: () => {
        setName('')
        setCommand('')
        setArgs('')
        setEnv('')
      },
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Plug className="h-5 w-5" />
          MCP servers
        </CardTitle>
        <CardDescription>
          Configure local MCP servers that Open Notebook can inspect and later expose to selected model workflows.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <LocalMCPDiscovery />

        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="mcp-name">Name</Label>
            <Input id="mcp-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="CodeGraph" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-command">Command</Label>
            <Input id="mcp-command" value={command} onChange={(event) => setCommand(event.target.value)} placeholder="codegraph-mcp" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-args">Arguments</Label>
            <Textarea id="mcp-args" value={args} onChange={(event) => setArgs(event.target.value)} placeholder="One argument per line" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-env">Non-secret environment</Label>
            <Textarea id="mcp-env" value={env} onChange={(event) => setEnv(event.target.value)} placeholder="KEY=value, one per line" />
          </div>
        </div>
        <Button onClick={submit} disabled={!name.trim() || !command.trim() || createServer.isPending}>
          {createServer.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Add stdio server
        </Button>

        {isError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>Could not load MCP servers.</AlertDescription>
          </Alert>
        )}

        <div className="space-y-3">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading MCP servers...</div>
          ) : servers.length === 0 ? (
            <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No MCP servers configured.
            </div>
          ) : (
            servers.map((server) => <MCPServerRow key={server.id || server.name} server={server} />)
          )}
        </div>
      </CardContent>
    </Card>
  )
}
