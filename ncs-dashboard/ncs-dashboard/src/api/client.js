import axios from 'axios'

const mockSetting = import.meta.env.VITE_USE_MOCK

// 开发环境默认 Mock，生产环境默认真实 API；生产发布不再因漏配环境变量而静默携带 Mock。
export const useMock = mockSetting == null
  ? import.meta.env.DEV
  : String(mockSetting).toLowerCase() === 'true'
export const useDemoData = useMock && String(import.meta.env.VITE_DEMO_DATA ?? 'false').toLowerCase() === 'true'
export const isDevelopment = import.meta.env.DEV

if (import.meta.env.PROD && mockSetting == null) {
  console.warn('[NCS Dashboard] VITE_USE_MOCK is not set in production; defaulting to real API mode.')
}

export class ApiRequestError extends Error {
  constructor(message, details = {}) {
    super(message)
    this.name = 'ApiRequestError'
    Object.assign(this, details)
  }
}

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 10000,
  headers: { Accept: 'application/json' }
})

function normalizeHttpError(error) {
  const body = error?.response?.data
  return new ApiRequestError(
    body?.message || error?.message || '网络或服务请求失败',
    {
      httpStatus: error?.response?.status ?? null,
      code: body?.code ?? null,
      requestId: body?.meta?.requestId ?? null,
      errors: Array.isArray(body?.errors) ? body.errors : [],
      cause: error
    }
  )
}

http.interceptors.response.use(
  (response) => response.data,
  (error) => Promise.reject(normalizeHttpError(error))
)
