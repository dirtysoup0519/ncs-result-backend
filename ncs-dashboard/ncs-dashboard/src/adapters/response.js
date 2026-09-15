const REQUIRED_SUCCESS_META = [
  'requestId',
  'dataVersion',
  'dataDate',
  'generatedAt',
  'staleness',
  'empty',
  'partial'
]

const STALENESS = new Set(['FRESH', 'STALE', 'UNKNOWN'])
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/
const OFFSET_TIMESTAMP_PATTERN = /T.*(?:Z|[+-]\d{2}:\d{2})$/

export class ApiProtocolError extends Error {
  constructor(message, response = null) {
    super(message)
    this.name = 'ApiProtocolError'
    this.response = response
    this.requestId = response?.meta?.requestId ?? null
  }
}

function assertNullableString(value, field) {
  if (value !== null && typeof value !== 'string') {
    throw new ApiProtocolError(`${field} must be a string or null`)
  }
}

export function isValidBusinessDate(value) {
  if (typeof value !== 'string' || !DATE_PATTERN.test(value)) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
}

export function assertBusinessDate(value, field, { nullable = true } = {}) {
  if (value === null && nullable) return value
  if (!isValidBusinessDate(value)) {
    throw new ApiProtocolError(`${field} must be a valid YYYY-MM-DD${nullable ? ' or null' : ''}`)
  }
  return value
}

export function assertOffsetTimestamp(value, field) {
  if (typeof value !== 'string' || !OFFSET_TIMESTAMP_PATTERN.test(value) || Number.isNaN(Date.parse(value))) {
    throw new ApiProtocolError(`${field} must be an ISO 8601 timestamp with timezone`)
  }
  return value
}

export function assertSuccessEnvelope(response) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) {
    throw new ApiProtocolError('API response is not an object', response)
  }
  if (response.code !== 'OK') {
    throw new ApiProtocolError(`Expected code="OK", got ${String(response.code)}`, response)
  }
  if (!response.meta || typeof response.meta !== 'object' || Array.isArray(response.meta)) {
    throw new ApiProtocolError('Missing success meta', response)
  }
  for (const key of REQUIRED_SUCCESS_META) {
    if (!(key in response.meta)) throw new ApiProtocolError(`Missing meta.${key}`, response)
  }

  const { meta } = response
  if (typeof meta.requestId !== 'string' || !meta.requestId.trim()) {
    throw new ApiProtocolError('meta.requestId must be a non-empty string', response)
  }
  assertNullableString(meta.dataVersion, 'meta.dataVersion')
  assertBusinessDate(meta.dataDate, 'meta.dataDate', { nullable: true })
  assertOffsetTimestamp(meta.generatedAt, 'meta.generatedAt')
  if (!STALENESS.has(meta.staleness)) {
    throw new ApiProtocolError('meta.staleness must be FRESH, STALE or UNKNOWN', response)
  }
  if (typeof meta.empty !== 'boolean') throw new ApiProtocolError('meta.empty must be boolean', response)
  if (typeof meta.partial !== 'boolean') throw new ApiProtocolError('meta.partial must be boolean', response)
  return response
}

export function adaptEnvelope(response, adapter = (data) => data) {
  try {
    assertSuccessEnvelope(response)
    return { data: adapter(response.data, response.meta), meta: response.meta }
  } catch (error) {
    // 无论错误发生在公共 envelope/meta 还是业务 DTO，都尽量保留原响应与 requestId，
    // 这样真实 Flask 联调时可以直接对应后端日志。
    if (error && typeof error === 'object') {
      if (!('response' in error) || error.response == null) error.response = response
      if (!('requestId' in error) || error.requestId == null) error.requestId = response?.meta?.requestId ?? null
    }
    throw error
  }
}
