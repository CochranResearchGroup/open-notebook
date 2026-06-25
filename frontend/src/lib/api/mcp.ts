import apiClient from './client'
import type {
  MCPServer,
  MCPServerInput,
  MCPLocalDiscovery,
  MCPServerTestResult,
  MCPToolCallInput,
  MCPToolCallResult,
} from '@/lib/types/mcp'

export const mcpApi = {
  listServers: async () => {
    const response = await apiClient.get<MCPServer[]>('/mcp/servers')
    return response.data
  },

  discoverLocalServers: async () => {
    const response = await apiClient.get<MCPLocalDiscovery>('/mcp/discover-local')
    return response.data
  },

  importLocalServer: async (candidateId: string, enabled = true) => {
    const response = await apiClient.post<MCPServer>('/mcp/import-local', {
      candidate_id: candidateId,
      enabled,
    })
    return response.data
  },

  createServer: async (data: MCPServerInput) => {
    const response = await apiClient.post<MCPServer>('/mcp/servers', data)
    return response.data
  },

  updateServer: async (id: string, data: Partial<MCPServerInput>) => {
    const response = await apiClient.put<MCPServer>(`/mcp/servers/${id}`, data)
    return response.data
  },

  deleteServer: async (id: string) => {
    const response = await apiClient.delete<{ deleted: boolean }>(`/mcp/servers/${id}`)
    return response.data
  },

  testServer: async (id: string) => {
    const response = await apiClient.post<MCPServerTestResult>(`/mcp/servers/${id}/test`)
    return response.data
  },

  callTool: async (data: MCPToolCallInput) => {
    const response = await apiClient.post<MCPToolCallResult>('/mcp/tool-call', data)
    return response.data
  },
}
