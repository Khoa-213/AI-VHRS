import { ApiError } from './api'

/**
 * Vietnam's provinces, districts and wards for the delivery address, from the public provinces.open-api.vn (v1: three
 * levels, codes of the General Statistics Office). The backend has no location endpoint of its own. These codes are the
 * ones its tests use and the mock carriers accept, and GHTK addresses by the names given here. A real GHN (LIVE) wants
 * GHN's own district and ward ids, which needs a location endpoint on the backend.
 */
const BASE = 'https://provinces.open-api.vn/api/v1'

export interface Place {
  code: string
  name: string
}

interface RawPlace { code: number; name: string }

// One request per list for the whole session; a failed one is asked again next time.
const cache = new Map<string, Promise<Place[]>>()

function load(path: string, pick?: 'districts' | 'wards'): Promise<Place[]> {
  let p = cache.get(path)
  if (!p) {
    p = (async () => {
      let res: Response
      try {
        res = await fetch(BASE + path)
      } catch (e) {
        throw new ApiError(0, 'NETWORK', e instanceof Error ? e.message : 'Network error')
      }
      if (!res.ok) throw new ApiError(res.status, 'PLACES_UNAVAILABLE', `Places failed (${res.status})`)
      const data = (await res.json()) as RawPlace[] | Partial<Record<'districts' | 'wards', RawPlace[]>>
      const list = Array.isArray(data) ? data : pick ? data[pick] ?? [] : []
      return list.map((x) => ({ code: String(x.code), name: x.name }))
    })()
    cache.set(path, p)
    p.catch(() => cache.delete(path))
  }
  return p
}

export const getProvinces = () => load('/p/')
export const getDistricts = (provinceCode: string) => load(`/p/${encodeURIComponent(provinceCode)}?depth=2`, 'districts')
export const getWards = (districtCode: string) => load(`/d/${encodeURIComponent(districtCode)}?depth=2`, 'wards')
