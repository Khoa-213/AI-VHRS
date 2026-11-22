import { api } from './api'

/**
 * Vietnam's provinces and wards for an address, from the backend (`GET /locations/provinces`, `.../{code}/wards`): GHN's
 * two-level catalogue (no district level since 01/07/2025), served from the API's cache so the carrier's token stays on
 * the server. Send `code` as `province_code` / `ward_code`; the backend fills in the names when it saves an address.
 * Signed-in only. `503 LOCATIONS_UNAVAILABLE` when the catalogue cannot be read, `404 PROVINCE_NOT_FOUND` for an unknown code.
 */
export interface Place {
  code: string
  name: string
}

// One request per list for the whole session; a failed one is asked again next time.
const cache = new Map<string, Promise<Place[]>>()

function load(path: string): Promise<Place[]> {
  let p = cache.get(path)
  if (!p) {
    p = api<Place[]>(path).then((list) => list.map((x) => ({ code: String(x.code), name: x.name })))
    cache.set(path, p)
    p.catch(() => cache.delete(path))
  }
  return p
}

export const getProvinces = () => load('/locations/provinces')
export const getWards = (provinceCode: string) => load(`/locations/provinces/${encodeURIComponent(provinceCode)}/wards`)
