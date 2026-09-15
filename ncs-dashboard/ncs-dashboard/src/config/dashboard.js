import { ApiProtocolError, isValidBusinessDate } from '../adapters/response.js'

function text(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

export function predictionRequestParams() {
  const date = text(import.meta.env.VITE_PREDICTION_DATE)
  const cutoffText = text(import.meta.env.VITE_PREDICTION_CUTOFF_HOUR)
  const cutoffHour = cutoffText === null ? null : Number(cutoffText)

  if (!date || !isValidBusinessDate(date)) {
    throw new ApiProtocolError('loadPrediction is available, but VITE_PREDICTION_DATE is not configured as a valid YYYY-MM-DD')
  }
  if (!Number.isInteger(cutoffHour) || cutoffHour < 0 || cutoffHour > 23) {
    throw new ApiProtocolError('loadPrediction is available, but VITE_PREDICTION_CUTOFF_HOUR is not an integer in [0, 23]')
  }
  return { date, cutoffHour }
}
