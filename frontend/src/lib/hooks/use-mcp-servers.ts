import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { mcpApi } from '@/lib/api/mcp'
import { useToast } from '@/lib/hooks/use-toast'
import { getApiErrorMessage } from '@/lib/utils/error-handler'
import type { MCPServerInput, MCPToolCallInput } from '@/lib/types/mcp'

export const MCP_QUERY_KEYS = {
  servers: ['mcp', 'servers'] as const,
  localDiscovery: ['mcp', 'local-discovery'] as const,
}

export function useMCPServers() {
  return useQuery({
    queryKey: MCP_QUERY_KEYS.servers,
    queryFn: () => mcpApi.listServers(),
  })
}

export function useCreateMCPServer() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  return useMutation({
    mutationFn: (data: MCPServerInput) => mcpApi.createServer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.servers })
      toast({ title: 'MCP server saved' })
    },
    onError: (error: unknown) => {
      toast({
        title: 'Could not save MCP server',
        description: getApiErrorMessage(error, (key) => key, 'Unknown error'),
        variant: 'destructive',
      })
    },
  })
}

export function useDiscoverLocalMCPServers() {
  return useQuery({
    queryKey: MCP_QUERY_KEYS.localDiscovery,
    queryFn: () => mcpApi.discoverLocalServers(),
  })
}

export function useImportLocalMCPServer() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  return useMutation({
    mutationFn: (candidateId: string) => mcpApi.importLocalServer(candidateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.servers })
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.localDiscovery })
      toast({ title: 'MCP server imported' })
    },
    onError: (error: unknown) => {
      toast({
        title: 'Could not import MCP server',
        description: getApiErrorMessage(error, (key) => key, 'Unknown error'),
        variant: 'destructive',
      })
    },
  })
}

export function useUpdateMCPServer() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<MCPServerInput> }) =>
      mcpApi.updateServer(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.servers })
      toast({ title: 'MCP server updated' })
    },
    onError: (error: unknown) => {
      toast({
        title: 'Could not update MCP server',
        description: getApiErrorMessage(error, (key) => key, 'Unknown error'),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteMCPServer() {
  const queryClient = useQueryClient()
  const { toast } = useToast()

  return useMutation({
    mutationFn: (id: string) => mcpApi.deleteServer(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MCP_QUERY_KEYS.servers })
      toast({ title: 'MCP server removed' })
    },
    onError: (error: unknown) => {
      toast({
        title: 'Could not remove MCP server',
        description: getApiErrorMessage(error, (key) => key, 'Unknown error'),
        variant: 'destructive',
      })
    },
  })
}

export function useTestMCPServer() {
  return useMutation({
    mutationFn: (id: string) => mcpApi.testServer(id),
  })
}

export function useCallMCPTool() {
  return useMutation({
    mutationFn: (data: MCPToolCallInput) => mcpApi.callTool(data),
  })
}
