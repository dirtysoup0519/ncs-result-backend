import { http, useMock } from './client'
import { mockGet } from '../mock/service'

const get = (key, path, params) => useMock ? mockGet(key, params) : http.get(path, { params })

export const metadataApi = {
  getCapabilities: () => get('capabilities', '/meta/capabilities'),
  getFilterOptions: (topic) => get('filterOptions', '/meta/filter-options', { topic }),
  getManifest: () => get('manifest', '/dashboard/manifest')
}
