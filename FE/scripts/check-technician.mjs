import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'
import { webcrypto } from 'node:crypto'

// Exercise the service against backend-shaped responses without network calls or real account credentials.
const source = readFileSync(new URL('../src/services/technician.ts', import.meta.url), 'utf8')
const output = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code }
}
function service(api, extras = {}) {
  const context = { exports: {}, URLSearchParams, crypto: webcrypto, TextDecoder, AbortController, setTimeout, clearTimeout, ...extras, require: (name) => {
    assert.equal(name, './api')
    return { api, ApiError }
  } }
  vm.runInNewContext(output, context)
  return context.exports
}
const raw = (id = 1) => ({
  id, order_id: 42, order_code: 'VH-0042', robot_id: 3, robot_code: 'FR3-03',
  technician_id: 17, technician_name: 'Tech', status: 'PREPARING', is_rewrite: false,
  slot_start: '2026-10-22T01:00:00Z', slot_end: '2026-10-22T01:30:00Z', estimated_duration_min: 30,
  progress_pct: 0, downloaded_at: null, started_at: null, finished_at: null, simulation_passed: false,
})

test('verified package hashes the downloaded bytes, omits credentials and rejects a tampered file', async () => {
  const bytes = new TextEncoder().encode(JSON.stringify({ format: 'test-format', pages: [{ paper: { width_mm: 100, height_mm: 150 }, strokes: [{ points: [[0, 0], [10, 10]] }] }] })).buffer
  const hash = Buffer.from(await webcrypto.subtle.digest('SHA-256', bytes)).toString('hex')
  const info = { job_id: 9, package_hash: hash, trajectory_format: 'test-format', pages: 1, trajectory_url: 'https://storage.test/signed' }
  let storageOptions
  const api = service(async (path) => { assert.equal(path, '/technician/jobs/9/package'); return info }, {
    fetch: async (url, opts) => { assert.equal(url, info.trajectory_url); storageOptions = opts; return { ok: true, arrayBuffer: async () => bytes } },
  })
  const result = await api.downloadJobPackage(9)
  assert.equal(result.hash, hash)
  assert.equal(result.pages.length, 1)
  assert.equal(storageOptions.credentials, 'omit')
  assert.equal(storageOptions.headers, undefined)
  await assert.rejects(() => api.verifyPackageBytes(new TextEncoder().encode('tampered').buffer, hash), (e) => e.code === 'JOB_HASH_MISMATCH')
})

test('package HTTP expiration does not return verified data and retries request a fresh package', async () => {
  let count = 0
  const api = service(async () => { count++; return { trajectory_url: 'https://storage.test/expired' } }, { fetch: async () => ({ ok: false, status: 403 }) })
  await assert.rejects(() => api.downloadJobPackage(9), (e) => e.code === 'STORAGE_DOWNLOAD_FAILED')
  await assert.rejects(() => api.downloadJobPackage(9), (e) => e.code === 'STORAGE_DOWNLOAD_FAILED')
  assert.equal(count, 2)
})

test('start requires a matching locally verified hash, current calibration, passed simulation and server permission', () => {
  const api = service(async () => {})
  const job = { status: 'PREPARING', packageHash: 'verified', downloadedAt: 'now', calibration: { is_valid: true }, simulationPassed: true, canStart: true }
  assert.equal(api.jobPermissions(job).start, false)
  assert.equal(api.jobPermissions(job, 'wrong').start, false)
  assert.equal(api.jobPermissions(job, 'verified').start, true)
  for (const change of [{ calibration: null }, { simulationPassed: null }, { simulationPassed: false }, { canStart: false }, { status: 'PAUSED' }, { downloadedAt: null }]) {
    assert.equal(api.jobPermissions({ ...job, ...change }, 'verified').start, false)
  }
})

test('state gates allow resume, safety events and force summary only in backend-supported states', async () => {
  const api = service(async () => {})
  assert.equal(api.eventAllowed('PAUSED', 'RESUME'), true)
  assert.equal(api.eventAllowed('WRITING', 'RESUME'), false)
  assert.equal(api.eventAllowed('WRITTEN', 'FORCE_SUMMARY'), true)
  assert.equal(api.eventAllowed('WRITTEN', 'PROGRESS'), false)
  assert.equal(api.eventAllowed('PREPARING', 'ESTOP'), false)
  assert.equal(api.eventAllowed('PAUSED', 'ESTOP'), true)
  assert.throws(() => api.postJobEvent(9, { event_type: 'WRITTEN' }), /invalidEvent/)
})

test('photo submission requires overall plus close-up, every live photo PASS and at most ten photos', () => {
  const api = service(async () => {})
  const overall = { kind: 'OVERALL', qc_result: 'PASS' }
  const close = { kind: 'CLOSE_UP', qc_result: 'PASS' }
  assert.equal(api.photosReady([overall]), false)
  assert.equal(api.photosReady([overall, overall]), false)
  assert.equal(api.photosReady([overall, { ...close, qc_result: null }]), false)
  assert.equal(api.photosReady([overall, { ...close, qc_result: 'FAIL' }]), false)
  assert.equal(api.photosReady([overall, close]), true)
  assert.equal(api.photosReady([overall, close, ...Array(9).fill(close)]), false)
})

test('photo binary upload is a raw signed request without bearer headers; registration is separate and retryable', async () => {
  const requests = []
  class XHR {
    upload = {}
    status = 200
    headers = {}
    open(method, url) { this.method = method; this.url = url }
    setRequestHeader(k, v) { this.headers[k] = v }
    send(file) { requests.push(this); assert.equal(file.type, 'image/png'); this.upload.onprogress({ lengthComputable: true, loaded: 10, total: 10 }); this.onload() }
  }
  const calls = []
  const api = service(async (...args) => { calls.push(args); return { id: 1 } }, { XMLHttpRequest: XHR })
  let progress = 0
  await api.uploadPhotoBinary({ method: 'PUT', upload_url: 'https://storage.test/signed' }, { type: 'image/png' }, (n) => { progress = n })
  assert.equal(progress, 100)
  assert.equal(requests[0].method, 'PUT')
  assert.deepEqual(requests[0].headers, { 'Content-Type': 'image/png' })
  assert.equal(calls.length, 0)
  await api.registerPhoto(9, 'same-photo-key', 'OVERALL')
  await api.registerPhoto(9, 'same-photo-key', 'OVERALL')
  assert.equal(calls[0][0], '/technician/jobs/9/photos')
  assert.equal(calls[0][1].body.photo_key, calls[1][1].body.photo_key)
  assert.equal(requests.length, 1)
})

test('job actions preserve HTTP verbs, endpoint paths and payloads throughout production and QC', async () => {
  const calls = []
  const api = service(async (path, opts) => { calls.push({ path, opts }); return raw(9) })
  await api.prepareJob(9)
  await api.calibrateJob(9, { checklist: { force_zeroed: true }, force_zero_offset: 0, probe_points: [] })
  await api.simulateJob(9, { passed: false, errors: ['collision'] })
  await api.startJob(9)
  await api.postJobEvent(9, { event_type: 'PROGRESS', progress_pct: 42 })
  await api.finishJob(9)
  await api.setPhotoQc(9, 3, 'FAIL', ' blurred ')
  await api.removePhoto(9, 3)
  await api.submitPhotos(9)
  await api.failJobQc(9, ' defect ')
  await api.reportIncident(9, { type: 'ROBOT', description: 'Stopped', robot_status_after: 'MAINTENANCE' })
  assert.deepEqual(calls.map((c) => [c.path, c.opts.method]), [
    ['/technician/jobs/9/prepare', 'POST'], ['/technician/jobs/9/calibration', 'POST'], ['/technician/jobs/9/simulation', 'POST'],
    ['/technician/jobs/9/start', 'POST'], ['/technician/jobs/9/events', 'POST'], ['/technician/jobs/9/finish', 'POST'],
    ['/technician/jobs/9/photos/3', 'PATCH'], ['/technician/jobs/9/photos/3', 'DELETE'], ['/technician/jobs/9/photos/submit', 'POST'],
    ['/technician/jobs/9/qc-fail', 'POST'], ['/technician/jobs/9/incidents', 'POST'],
  ])
  assert.equal(calls[6].opts.body.qc_note, 'blurred')
  assert.equal(calls[9].opts.body.note, 'defect')
})

test('uses authenticated technician endpoint, repeated status filters and date pagination', async () => {
  const api = service(async (path) => {
    const url = new URL(path, 'https://example.test')
    assert.equal(url.pathname, '/technician/jobs')
    assert.deepEqual(url.searchParams.getAll('status'), ['WRITING', 'PAUSED'])
    assert.equal(url.searchParams.get('from'), '2026-10-22T00:00:00+07:00')
    assert.equal(url.searchParams.get('to'), '2026-10-23T00:00:00+07:00')
    assert.equal(url.searchParams.get('page'), '2')
    assert.equal(url.searchParams.get('page_size'), '20')
    assert.equal(url.searchParams.has('technician_id'), false)
    return { items: [raw()], total: 21, page: 2, page_size: 20 }
  })
  const result = await api.listTechJobs({ status: ['WRITING', 'PAUSED'], from: '2026-10-22T00:00:00+07:00', to: '2026-10-23T00:00:00+07:00', page: 2, pageSize: 20 })
  assert.equal(result.total, 21)
  assert.equal(result.items[0].technicianId, 17)
  assert.equal(result.items[0].progress, 0)
  assert.equal(result.items[0].simulationPassed, false)
})

test('dashboard reads beyond the first 200 jobs and deduplicates a job moved between pages', async () => {
  const pages = []
  const api = service(async (path) => {
    const url = new URL(path, 'https://example.test')
    const page = Number(url.searchParams.get('page'))
    pages.push(page)
    return { items: page === 1 ? Array.from({ length: 200 }, (_, i) => raw(i + 1)) : [raw(200), raw(201)], total: 202, page, page_size: 200 }
  })
  const result = await api.allTechJobs()
  assert.deepEqual(pages, [1, 2])
  assert.equal(result.length, 201)
  assert.equal(result.at(-1).id, 201)
})

test('job detail keeps server state, nullable material names and a failed simulation', async () => {
  const calls = []
  const api = service(async (...args) => {
    calls.push(args)
    return { ...raw(9), order_type: 'OT3_TEMPLATE', quantity: 4, eta: null,
      paper_name: 'A5', pen_name: null, ink_name: null, approach_note: 'Customer instructions',
      calibration: { id: 2, is_valid: true, created_at: '2026-10-22T01:00:00Z' }, can_start: false, incidents: [] }
  })
  const job = await api.getTechJob(9)
  assert.equal(job.orderId, 42)
  assert.equal(job.quantity, 4)
  assert.equal(job.paper, 'A5')
  assert.equal(job.pen, null)
  assert.equal(job.canStart, false)
  assert.equal(job.simulationPassed, false)
  assert.equal(job.calibration.is_valid, true)
  assert.deepEqual(calls, [['/technician/jobs/9', undefined]]) // Reading details must never download, prepare or start a job.
})

test('permission and missing-job errors propagate instead of becoming empty data', async () => {
  for (const status of [403, 404]) {
    const error = Object.assign(new Error('Backend error'), { status })
    const api = service(async () => { throw error })
    await assert.rejects(() => api.getTechJob(9), (e) => e === error)
    await assert.rejects(() => api.allTechJobs(), (e) => e === error)
  }
})

test('Retry-After blocks subsequent technician requests rather than hammering a rate-limited backend', async () => {
  const error = new ApiError(429, 'RATE_LIMITED', 'Rate limited')
  error.retryAfterMs = 60000
  let count = 0
  const api = service(async () => { count++; throw error })
  await assert.rejects(() => api.getTechJob(9), (e) => e === error)
  await assert.rejects(() => api.listTechJobs(), (e) => e === error)
  assert.equal(count, 1)
})

test('calibration plane and optional JSON reject invalid measurements without inventing defaults', () => {
  const code = ts.transpileModule(readFileSync(new URL('../src/pages/tech/flow.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
  const context = { exports: {}, require: () => ({ ApiError }) }
  vm.runInNewContext(code, context)
  const { probePlaneValid, optionalJson } = context.exports
  assert.equal(probePlaneValid([{ x: 0, y: 0, z: 0 }, { x: 10, y: 0, z: 0 }, { x: 0, y: 10, z: 0 }]), true)
  assert.equal(probePlaneValid([{ x: 0, y: 0, z: 0 }, { x: 10, y: 0, z: 0 }, { x: 20, y: 0, z: 0 }]), false)
  assert.equal(probePlaneValid([{ x: 0, y: 0, z: 0 }, { x: NaN, y: 0, z: 0 }, { x: 0, y: 10, z: 0 }]), false)
  assert.equal(optionalJson(''), undefined)
  assert.throws(() => optionalJson('[]'), /invalidJson/)
  assert.throws(() => optionalJson('null'), /invalidJson/)
  assert.throws(() => optionalJson('{invalid}'), /invalidJson/)
  assert.equal(Array.isArray(optionalJson('[]', true)), true)
})
