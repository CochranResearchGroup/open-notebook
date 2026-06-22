import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { modelsApi } from '@/lib/api/models'
import { useToast } from '@/lib/hooks/use-toast'
import { useTranslation } from '@/lib/hooks/use-translation'
import { getApiErrorKey } from '@/lib/utils/error-handler'
import { CodexMCPProfileUpdate, CreateModelRequest, ModelDefaults, ModelTestResult } from '@/lib/types/models'

export const MODEL_QUERY_KEYS = {
  models: ['models'] as const,
  model: (id: string) => ['models', id] as const,
  defaults: ['models', 'defaults'] as const,
  providers: ['models', 'providers'] as const,
  codexAppServer: ['models', 'codex-app-server'] as const,
  codexMcpProfile: ['models', 'codex-app-server', 'mcp-profile'] as const,
}

export function useModels() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.models,
    queryFn: () => modelsApi.list(),
  })
}

export function useModel(id: string) {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.model(id),
    queryFn: () => modelsApi.get(id),
    enabled: !!id,
  })
}

export function useCreateModel() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CreateModelRequest) => modelsApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      toast({
        title: t('common.success'),
        description: t('models.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useDeleteModel() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (id: string) => modelsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      queryClient.invalidateQueries({ queryKey: ['credentials'] })
      toast({
        title: t('common.success'),
        description: t('models.deleteSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useModelDefaults() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.defaults,
    queryFn: () => modelsApi.getDefaults(),
  })
}

export function useUpdateModelDefaults() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: Partial<ModelDefaults>) => modelsApi.updateDefaults(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      toast({
        title: t('common.success'),
        description: t('models.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useProviders() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.providers,
    queryFn: () => modelsApi.getProviders(),
  })
}

export function useCodexAppServerStatus() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.codexAppServer,
    queryFn: () => modelsApi.getCodexAppServerStatus(),
  })
}

export function useSyncCodexAppServer() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: () => modelsApi.syncCodexAppServer(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.providers })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.codexAppServer })
      toast({
        title: t('common.success'),
        description: result.new > 0
          ? t('models.syncSuccess')
            .replace('{discovered}', result.discovered.toString())
            .replace('{new}', result.new.toString())
          : t('models.syncNoNew').replace('{count}', result.discovered.toString()),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('models.syncFailed')),
        variant: 'destructive',
      })
    },
  })
}

export function useSetCodexAppServerDefaults() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: () => modelsApi.setCodexAppServerDefaults(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.models })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.codexAppServer })
      toast({
        title: t('common.success'),
        description: t('models.saveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useCodexMCPProfile() {
  return useQuery({
    queryKey: MODEL_QUERY_KEYS.codexMcpProfile,
    queryFn: () => modelsApi.getCodexMCPProfile(),
  })
}

export function useUpdateCodexMCPProfile() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (data: CodexMCPProfileUpdate) => modelsApi.updateCodexMCPProfile(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.codexMcpProfile })
      toast({
        title: t('common.success'),
        description: t('models.codexMcpProfileSaveSuccess'),
      })
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useAutoAssignDefaults() {
  const queryClient = useQueryClient()
  const { toast } = useToast()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: () => modelsApi.autoAssign(),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: MODEL_QUERY_KEYS.defaults })

      const assignedCount = Object.keys(result.assigned).length
      const missingCount = result.missing.length

      if (assignedCount > 0) {
        toast({
          title: t('common.success'),
          description: t('models.autoAssignSuccess').replace('{count}', assignedCount.toString()),
        })
      } else if (missingCount > 0) {
        toast({
          title: t('common.warning'),
          description: t('models.autoAssignNoModels'),
          variant: 'destructive',
        })
      } else {
        toast({
          title: t('common.success'),
          description: t('models.autoAssignAlreadySet'),
        })
      }
    },
    onError: (error: unknown) => {
      toast({
        title: t('common.error'),
        description: getApiErrorKey(error, t('common.error')),
        variant: 'destructive',
      })
    },
  })
}

export function useTestModel() {
  const [testResult, setTestResult] = useState<ModelTestResult | null>(null)
  const [testedModelName, setTestedModelName] = useState('')
  const [testingModelId, setTestingModelId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: (modelId: string) => modelsApi.testModel(modelId),
    onSuccess: (result) => {
      setTestResult(result)
      setTestingModelId(null)
    },
    onError: (error: unknown) => {
      const msg = error instanceof Error ? error.message : String(error)
      setTestResult({ success: false, message: msg })
      setTestingModelId(null)
    },
  })

  const testModel = useCallback((modelId: string, modelName: string) => {
    setTestedModelName(modelName)
    setTestingModelId(modelId)
    setTestResult(null)
    mutation.mutate(modelId)
  }, [mutation])

  const clearResult = useCallback(() => {
    setTestResult(null)
    setTestedModelName('')
    setTestingModelId(null)
  }, [])

  return {
    testModel,
    isPending: mutation.isPending,
    testingModelId,
    testResult,
    testedModelName,
    clearResult,
  }
}
