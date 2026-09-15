export class DecimalProtocolError extends Error {
  constructor(field, value, message = 'invalid numeric value') {
    super(`${message} for ${field}: ${String(value)}`)
    this.name = 'DecimalProtocolError'
    this.field = field
    this.value = value
  }
}

const DECIMAL_PATTERN = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/

export function toDecimalNumber(value, field = 'value', { nullable = true } = {}) {
  if (value === null || value === undefined) {
    if (nullable) return null
    throw new DecimalProtocolError(field, value, 'null is not allowed')
  }
  if (typeof value !== 'string') {
    throw new DecimalProtocolError(field, value, 'decimal string expected')
  }
  const text = value.trim()
  if (!text) throw new DecimalProtocolError(field, value, 'empty string is not allowed')
  if (!DECIMAL_PATTERN.test(text)) throw new DecimalProtocolError(field, value, 'decimal string expected')
  const parsed = Number(text)
  if (!Number.isFinite(parsed)) throw new DecimalProtocolError(field, value)
  return parsed
}

export function toNonNegativeDecimalNumber(value, field = 'value', { nullable = true } = {}) {
  const parsed = toDecimalNumber(value, field, { nullable })
  if (parsed !== null && parsed < 0) {
    throw new DecimalProtocolError(field, value, 'non-negative decimal expected')
  }
  return parsed
}

export function toInteger(value, field = 'value', { nullable = false } = {}) {
  if (value === null || value === undefined) {
    if (nullable) return null
    throw new DecimalProtocolError(field, value, 'null is not allowed')
  }
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    throw new DecimalProtocolError(field, value, 'JSON integer expected')
  }
  return value
}

export function toNonNegativeInteger(value, field = 'value', { nullable = false } = {}) {
  const parsed = toInteger(value, field, { nullable })
  if (parsed !== null && parsed < 0) {
    throw new DecimalProtocolError(field, value, 'non-negative JSON integer expected')
  }
  return parsed
}

export function toRatio(value, field = 'ratio', { nullable = true } = {}) {
  const parsed = toDecimalNumber(value, field, { nullable })
  if (parsed === null) return null
  if (parsed < 0 || parsed > 1) {
    throw new DecimalProtocolError(field, value, 'ratio must be in [0, 1]')
  }
  return parsed
}

export function toPercent(value, field = 'ratio', { nullable = true } = {}) {
  const ratio = toRatio(value, field, { nullable })
  return ratio === null ? null : ratio * 100
}

export function assertPrecision(value, field = 'precision') {
  const parsed = toInteger(value, field)
  if (parsed < 0 || parsed > 10) {
    throw new DecimalProtocolError(field, value, 'precision must be an integer in [0, 10]')
  }
  return parsed
}

export function formatNumber(value, precision = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision
  })
}
