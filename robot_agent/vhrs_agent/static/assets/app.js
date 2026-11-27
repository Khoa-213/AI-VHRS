/* VHRS workstation: the technician's only workspace (owner 2026-11-26, BE/docs/FE_TECH_WORKSPACE_HANDOFF.md section 2).
 * Plain JS, no build. Backend business calls go through this agent: /api/technician/<path> (the person's own token).
 * This machine's robot is driven through the agent's own API (/api/jobs/{id}/load, preflight, dry-run, run, real-enable, ...).
 * REAL is switched on here only (button, c1); the backend has no command for it. Software STOP never replaces the physical E-Stop. */
'use strict';

const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const store = {
  get(k) { try { return sessionStorage.getItem(k) || ''; } catch (e) { return ''; } },
  set(k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  clear() { try { ['vhrs_token', 'vhrs_role', 'vhrs_name', 'vhrs_app'].forEach((k) => sessionStorage.removeItem(k)); } catch (e) { /* private mode */ } },
};

// ─── State ───────────────────────────────────────────────────────────
const S = {
  bearer: store.get('vhrs_token'), role: store.get('vhrs_role'), name: store.get('vhrs_name'),
  viewerToken: new URLSearchParams(location.search).get('token') || '',
  agent: null, robots: null, robotsErr: '', jobs: null, jobsErr: '', robotFilter: null,
  sel: Number(new URLSearchParams(location.search).get('job')) || null, detail: null, detailErr: '',
  pkg: {}, loaded: {}, pre: {}, photos: {}, quality: {}, log: null,
  open: null, busy: false, f: { mode: '', realmin: '30', calTab: 'robot' }, calFile: null, calFileErr: '',
  snap: null, localJob: null, sig: '',
};

// ─── Words ───────────────────────────────────────────────────────────
const JOB_STATUS = { SCHEDULED: 'Đã xếp lịch', PREPARING: 'Đang chuẩn bị', WRITING: 'Đang viết', PAUSED: 'Tạm dừng', WRITTEN: 'Đã viết xong',
  PHOTO_UPLOADED: 'Đã gửi ảnh', DONE: 'Hoàn tất', FAILED: 'Thất bại', REWRITE_REQUIRED: 'Cần viết lại', CANCELLED: 'Đã huỷ' };
const ROBOT_STATE = { IDLE: 'Rảnh', PREPARING: 'Đang chuẩn bị', WRITING: 'Đang viết', PAUSED_SAFE: 'Đã dừng an toàn', DANGER: 'Nguy hiểm', OFFLINE: 'Ngoại tuyến' };
const LINK = { ONLINE: 'Đã kết nối', OFFLINE: 'Mất kết nối', UNKNOWN: 'Chưa từng kết nối' };
const OUT = { MAINTENANCE: 'Bảo trì', BROKEN: 'Hỏng' };
const MODE = { mock: 'MOCK (giả lập phần mềm)', sim: 'SIM (mô phỏng)', real: 'REAL (robot thật)' };
const ERR = {
  ROBOT_NOT_SELECTED: 'Hãy chọn robot cho job.',
  ROBOT_NOT_FOUND: 'Robot này không được giao cho bạn.',
  ROBOT_UNAVAILABLE: 'Robot đang bảo trì hoặc hỏng: chọn robot khác của bạn.',
  ROBOT_NOT_SUITABLE: 'Robot này không hợp loại bút của đơn.',
  SLOT_CONFLICT: 'Robot đã có job khác trong khung giờ này.',
  REAL_NOT_ENABLED_ON_SITE: 'Chưa bật REAL cho job này: bấm "Bật REAL" (bước 9).',
  DRY_RUN_REQUIRED: 'Cần một lần chạy thử nhấc bút đạt (bước 8) trước khi viết REAL.',
  AUTHORIZATION_REQUIRED: 'Thiếu mã xác nhận của kế hoạch: nạp job lại ở máy này (bước 5).',
  JOB_NOT_LOADED: 'Hãy nạp job ở máy này trước (bước 5). Chỉ người đã nạp job mới thao tác được.',
  JOB_NOT_DOWNLOADED: 'Hãy tải gói và kiểm hash trước (bước 1).',
  CALIBRATION_REQUIRED: 'Job chưa có hiệu chuẩn (bước 4).',
  MODE_DISABLED: 'Máy này không bật chế độ chạy đó.',
  AGENT_BUSY: 'Agent đang chạy một job: đợi xong hoặc DỪNG trước.',
  ROBOT_UNREACHABLE: 'Robot thật không phản hồi: REAL KHÔNG bật. Kiểm tra nguồn robot, controller sẵn sàng, dây mạng tới 192.168.58.2 rồi thử lại.',
  ROBOT_CONFIG_MISMATCH: '',                    // the agent's own message names what differs (tool slot, work object, ...)
  NO_RUN_ACTIVE: 'Chưa có lần chạy nào đang diễn ra.',
  BACKEND_UNREACHABLE: 'Agent không gọi được máy chủ. Kiểm tra mạng.',
  NETWORK: 'Không gọi được agent trên máy này.',
  UNAUTHENTICATED: 'Phiên đăng nhập đã hết: đăng nhập lại.',
  FORBIDDEN: 'Tài khoản này không được làm thao tác đó.',
  JOB_HASH_MISMATCH: 'Hash của file tải về không khớp: không dùng gói này, tải lại.',
};

class ApiErr extends Error {
  constructor(status, code, message, details) { super(message); this.status = status; this.code = code; this.details = details; }
}
const errText = (e) => (e && ERR[e.code]) || (e && e.message) || String(e);

// ─── API ─────────────────────────────────────────────────────────────
function hdr() { return S.bearer ? { Authorization: 'Bearer ' + S.bearer } : (S.viewerToken ? { 'X-Viewer-Token': S.viewerToken } : {}); }
window.apiHeaders = hdr;                                                   // twin.js reads it

async function api(path, { method = 'GET', body } = {}) {
  let r;
  try {
    r = await fetch(path, { method, headers: { ...hdr(), ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined });
  } catch (e) { throw new ApiErr(0, 'NETWORK', 'Không gọi được agent: ' + e.message); }
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
  if (!r.ok) {
    if (r.status === 401 && S.bearer) { logout(); }
    const er = (data && data.error) || (data && data.detail ? { message: typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail) } : {});
    throw new ApiErr(r.status, er.code || 'HTTP_' + r.status, er.message || 'Lỗi ' + r.status, er.details);
  }
  return data;
}
const tech = (path, opts) => api('/api/technician/' + path, opts);
const uuid = () => (crypto.randomUUID ? crypto.randomUUID() : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
  const r = Math.random() * 16 | 0; return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
}));

/** A robot command through the backend (any of my robots, also one at another workstation); waits for its answer. */
async function robotCommand(kind, target, params = {}, waitS = 60) {
  let cmd = await tech('robot-commands', { method: 'POST', body: { kind, ...target, params, idempotency_key: uuid() } });
  const end = Date.now() + waitS * 1000;
  while ((cmd.status === 'PENDING' || cmd.status === 'DELIVERED') && Date.now() < end) {
    await sleep(700);
    cmd = await tech('robot-commands/' + encodeURIComponent(cmd.id));
  }
  if (cmd.status === 'FAILED' || cmd.status === 'EXPIRED') throw new ApiErr(409, cmd.error_code || cmd.status, cmd.error_message || ('Lệnh ' + kind + ': ' + cmd.status));
  return cmd;
}

// ─── SHA-256 (the page may be opened over plain http on the LAN, where crypto.subtle is missing) ──
const K256 = [0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d,
  0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2];
function sha256js(bytes) {
  const n = bytes.length, total = ((n + 9 + 63) >> 6) << 6, m = new Uint8Array(total);
  m.set(bytes); m[n] = 0x80;
  const dv = new DataView(m.buffer);
  dv.setUint32(total - 4, (n * 8) >>> 0); dv.setUint32(total - 8, Math.floor(n / 0x20000000));
  const H = [0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19], W = new Uint32Array(64);
  const rot = (x, k) => (x >>> k) | (x << (32 - k));
  for (let i = 0; i < total; i += 64) {
    for (let t = 0; t < 16; t++) W[t] = dv.getUint32(i + t * 4);
    for (let t = 16; t < 64; t++) {
      const s0 = rot(W[t - 15], 7) ^ rot(W[t - 15], 18) ^ (W[t - 15] >>> 3), s1 = rot(W[t - 2], 17) ^ rot(W[t - 2], 19) ^ (W[t - 2] >>> 10);
      W[t] = (W[t - 16] + s0 + W[t - 7] + s1) | 0;
    }
    let [a, b, c, d, e, f, g, h] = H;
    for (let t = 0; t < 64; t++) {
      const t1 = (h + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K256[t] + W[t]) | 0;
      const t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
      h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    [a, b, c, d, e, f, g, h].forEach((v, k) => { H[k] = (H[k] + v) | 0; });
  }
  return H.map((x) => (x >>> 0).toString(16).padStart(8, '0')).join('');
}
async function sha256hex(bytes) {
  if (globalThis.crypto && crypto.subtle) {
    const d = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(d), (x) => x.toString(16).padStart(2, '0')).join('');
  }
  return sha256js(bytes);
}

// ─── Calibration file (read like robot_console.py calibrate) ─────────
const CHECKLIST = [['frame_mounted', 'Đã lắp khung'], ['paper_clamped', 'Đã kẹp giấy'], ['pen_installed', 'Đã lắp bút'], ['force_zeroed', 'Đã zero lực (bút nhấc lên)']];
function readCalibrationFile(text) {
  let raw;
  try { raw = JSON.parse(text.replace(/^﻿/, '')); } catch (e) { throw new Error('File này không phải calibration.json hợp lệ.'); }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('File này không phải calibration.json hợp lệ.');
  const strip = (x) => Array.isArray(x) ? x.map(strip)
    : (x && typeof x === 'object' ? Object.fromEntries(Object.entries(x).filter(([k]) => !k.startsWith('_')).map(([k, v]) => [k, strip(v)])) : x);
  const body = strip(raw), todo = [];
  const walk = (x, p) => {
    if (Array.isArray(x)) x.forEach((v, i) => walk(v, `${p}[${i}]`));
    else if (x && typeof x === 'object') Object.entries(x).forEach(([k, v]) => walk(v, p ? `${p}.${k}` : k));
    else if (x === null || (typeof x === 'string' && x.startsWith('<'))) todo.push(p);
  };
  walk(body, '');
  if (todo.length) throw new Error('calibration.json còn chỗ chưa điền: ' + todo.join(', '));
  if (!body.checklist || typeof body.checklist !== 'object' || typeof body.force_zero_offset !== 'number' || !Array.isArray(body.probe_points)) {
    throw new Error('calibration.json cần có checklist, force_zero_offset và probe_points.');
  }
  return body;
}
function planeOk(p) {
  if (p.length < 3 || p.slice(0, 3).some((q) => ![q.x, q.y, q.z].every(Number.isFinite))) return false;
  const [a, b, c] = p, u = [b.x - a.x, b.y - a.y, b.z - a.z], v = [c.x - a.x, c.y - a.y, c.z - a.z];
  return Math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]) > 1e-6;
}

// ─── Small views ─────────────────────────────────────────────────────
const fmt = (iso) => {
  if (!iso) return '—';
  const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso);
  return d.toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
};
const pill = (text, tone = '') => `<span class="pill ${tone}">${esc(text)}</span>`;
const linkTone = (c) => c === 'ONLINE' ? 'ok' : '';
const stateTone = (s) => s === 'DANGER' ? 'bad' : s === 'PAUSED_SAFE' ? 'warn' : s === 'IDLE' ? 'ok' : 'ink';
const levelTone = (l) => l >= 3 ? 'bad' : l === 2 ? 'warn' : '';
const jobTone = (s) => ['FAILED', 'REWRITE_REQUIRED', 'CANCELLED'].includes(s) ? 'bad' : ['WRITING', 'PAUSED'].includes(s) ? 'ink' : ['PHOTO_UPLOADED', 'DONE'].includes(s) ? 'ok' : '';
const val = (k, d = '') => (S.f[k] ?? d);
const checked = (k) => (S.f[k] ? 'checked' : '');
let toastTimer = null;
function toast(msg, bad = false) {
  const t = $('toast'); t.textContent = msg; t.className = bad ? 'bad' : ''; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, bad ? 9000 : 4000);
}

/** The robot this workstation drives: agent.json robot_id, or the robot of a job loaded here. */
function localRobotId() {
  if (S.agent && S.agent.robot_id) return S.agent.robot_id;
  const l = Object.values(S.loaded).find((x) => x && x.robot_id);
  return l ? l.robot_id : null;
}
const myRobot = (id) => ((S.robots && S.robots.robots) || []).find((r) => r.robot_id === id) || null;
const robotLabel = (id) => (id == null ? 'Chưa chọn robot' : (myRobot(id) || {}).robot_code || '#' + id);

// ─── Header, strip and job list ──────────────────────────────────────
function renderHeader() {
  const a = S.agent || {}, modes = (a.modes || []).map((m) => m.toUpperCase()).join(' / ');
  const rid = localRobotId();
  $('station').hidden = !a.modes;
  $('station').textContent = 'Máy này: ' + (rid ? robotLabel(rid) : 'chưa rõ robot') + (modes ? ' · ' + modes : '');
  const real = a.real_enabled;
  $('realbar').hidden = !real;
  if (real) {
    const left = Math.max(0, Math.round(real.expires_at - Date.now() / 1000));
    $('realtext').textContent = `REAL đang bật cho job ${real.job_id} tới ${fmt(real.expires_at)} (còn ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')})`
      + (real.waive_dry_run ? ' · BỎ chạy thử' : '');
  }
}

function renderStrip() {
  const m = S.robots;
  $('stripsum').textContent = m ? `Đang kết nối ${m.online} / ${m.total} · Đang hoạt động ${m.active}` : '';
  if (S.robotsErr && !m) { $('robots').innerHTML = `<p class="err">${esc(S.robotsErr)}</p>`; return; }
  if (!m) { $('robots').innerHTML = '<p class="hint">Đang tải…</p>'; return; }
  if (!m.robots.length) { $('robots').innerHTML = '<p class="hint">Bạn chưa được giao robot nào. Hãy nhờ quản lý giao robot.</p>'; return; }
  const local = localRobotId();
  $('robots').innerHTML = m.robots.map((r) => {
    const out = OUT[r.robot_status];
    const remoteLive = r.robot_id !== local && r.job_id && ['WRITING', 'PAUSED'].includes(r.job_status);
    return `<div class="robot${r.active ? ' active' : ''}${S.robotFilter === r.robot_id ? ' on' : ''}">
      <div class="head"><div><span class="code">${esc(r.robot_code)}</span>${r.station ? `<div class="hint">${esc(r.station)}</div>` : ''}</div>
        <div class="row" style="justify-content:flex-end">${r.robot_id === local ? pill('máy này', 'ink plain') : ''}${pill(LINK[r.connection_state] || LINK.UNKNOWN, linkTone(r.connection_state))}</div></div>
      <div class="pills">${r.active ? pill('Đang hoạt động', 'ink') : ''}${r.state !== 'OFFLINE' ? pill(ROBOT_STATE[r.state] || r.state, stateTone(r.state)) : ''}
        ${out ? pill(out, r.robot_status === 'BROKEN' ? 'bad' : 'warn') : ''}${(r.open_alerts || []).length ? pill(`${r.open_alerts.length} cảnh báo · mức ${r.level}`, levelTone(r.level)) : ''}
        ${(r.enabled_modes || []).map((x) => pill(x.toUpperCase(), 'plain')).join('')}${r.real_enabled ? pill('REAL đang bật · job ' + r.real_enabled.job_id, 'bad') : ''}</div>
      ${r.headline_vi ? `<div class="line">${esc(r.headline_vi)}</div>` : ''}
      <div class="acts">
        <button type="button" class="small" data-act="filter" data-id="${r.robot_id}">${S.robotFilter === r.robot_id ? 'Xem tất cả job' : 'Job của robot này'}</button>
        ${r.job_id ? `<button type="button" class="small" data-act="open" data-id="${r.job_id}">Mở job #${r.job_id}</button>` : ''}
        ${remoteLive ? `<button type="button" class="small" data-act="rcmd" data-kind="PAUSE" data-id="${r.robot_id}">Tạm dừng</button>
          <button type="button" class="small danger" data-act="rcmd" data-kind="STOP" data-id="${r.robot_id}">DỪNG</button>` : ''}
      </div></div>`;
  }).join('');
}

const GROUPS = [['Đang viết', ['WRITING', 'PAUSED']], ['Sẵn sàng', ['SCHEDULED', 'PREPARING']], ['Chờ QC', ['WRITTEN']],
  ['Cần chú ý', ['FAILED', 'REWRITE_REQUIRED']], ['Lịch sử', ['PHOTO_UPLOADED', 'DONE', 'CANCELLED']]];
function renderJobs() {
  const all = (S.jobs || []).filter((j) => S.robotFilter == null || j.robot_id === S.robotFilter);
  $('jobfilter').hidden = S.robotFilter == null;
  $('jobfilter').textContent = S.robotFilter == null ? '' : 'Đang xem các job của ' + robotLabel(S.robotFilter) + '.';
  if (S.jobsErr && !S.jobs) { $('joblist').innerHTML = `<p class="err">${esc(S.jobsErr)}</p>`; return; }
  if (!S.jobs) { $('joblist').innerHTML = '<p class="hint">Đang tải…</p>'; return; }
  if (!all.length) { $('joblist').innerHTML = '<p class="hint">Chưa có job nào.</p>'; return; }
  $('joblist').innerHTML = GROUPS.map(([title, sts]) => {
    const rows = all.filter((j) => sts.includes(j.status));
    if (!rows.length) return '';
    return `<h3><span>${title}</span><span>${rows.length}</span></h3>` + rows.map((j) => `
      <button type="button" class="jobbtn${j.id === S.sel ? ' on' : ''}" data-act="open" data-id="${j.id}" ${j.id === S.sel ? 'aria-current="true"' : ''}>
        <b>${esc(j.order_code || '#' + j.order_id)}</b>
        <span class="meta">Job #${j.id} · ${esc(robotLabel(j.robot_id))} · ${esc(fmt(j.slot_start))} · ${esc(JOB_STATUS[j.status] || j.status)}${j.progress_pct != null ? ' · ' + Math.round(j.progress_pct) + '%' : ''}</span>
      </button>`).join('');
  }).join('');
}

// ─── The open job: twelve steps ──────────────────────────────────────
const AFTER_PREPARE = ['PREPARING', 'WRITING', 'PAUSED', 'WRITTEN', 'PHOTO_UPLOADED', 'DONE'];
const AFTER_START = ['WRITING', 'PAUSED', 'WRITTEN', 'PHOTO_UPLOADED', 'DONE'];
const AFTER_FINISH = ['WRITTEN', 'PHOTO_UPLOADED', 'DONE'];

function steps(d) {
  const id = d.id, st = d.status, cal = !!(d.calibration && d.calibration.is_valid);
  const prepared = AFTER_PREPARE.includes(st), started = AFTER_START.includes(st), finished = AFTER_FINISH.includes(st);
  const pkgOk = !!(S.pkg[id] && S.pkg[id].ok), loaded = !!S.loaded[id], pre = !!(S.pre[id] && S.pre[id].ok);
  const sim = d.simulation_passed === true;
  const last = (S.agent && S.agent.last) || null;
  const dry = !!(last && last.job_id === id && last.dry_run && last.result && last.result.state === 'DRY_RUN_DONE');
  const realAvail = !!(S.agent && (S.agent.modes || []).includes('real'));
  const realOn = !!(S.agent && S.agent.real_enabled && S.agent.real_enabled.job_id === id);
  const local = localRobotId(), elsewhere = d.robot_id != null && local != null && d.robot_id !== local;
  return [
    { key: 'package', title: 'Tải gói và kiểm hash', done: prepared || (!!d.downloaded_at && pkgOk) },
    { key: 'robot', title: 'Chọn robot', done: d.robot_id != null, why: d.robot_id == null && st !== 'SCHEDULED' ? 'Chỉ chọn được khi job đã xếp lịch.' : '' },
    { key: 'prepare', title: 'Chuẩn bị', done: prepared, why: !(d.downloaded_at && pkgOk) ? 'Hãy tải gói và kiểm hash trước.' : d.robot_id == null ? 'Hãy chọn robot cho job.' : '' },
    { key: 'calibrate', title: 'Hiệu chuẩn', done: started || cal, why: prepared ? '' : 'Hãy bấm Chuẩn bị trước.' },
    { key: 'load', title: 'Nạp job vào máy này', done: started || loaded,
      why: elsewhere ? `Job dùng robot ${robotLabel(d.robot_id)} ở máy trạm khác.` : cal ? '' : 'Hãy gửi hiệu chuẩn trước.' },
    { key: 'preflight', title: 'Kiểm tra trước', done: started || pre, why: loaded ? '' : 'Hãy nạp job trước.' },
    { key: 'simulate', title: 'Ghi kết quả mô phỏng', done: started || sim, why: !cal ? 'Hãy gửi hiệu chuẩn trước.' : (!pre && !sim) ? 'Hãy chạy Kiểm tra trước.' : '' },
    { key: 'dryRun', title: 'Chạy thử nhấc bút', done: started || dry, why: sim || started ? '' : 'Hãy ghi kết quả mô phỏng đạt trước.' },
    { key: 'real', title: 'Bật REAL (chỉ khi chạy robot thật)', optional: true, done: realOn,
      why: !realAvail ? 'Máy này không nối robot thật: bỏ qua khi chạy SIM.' : loaded ? '' : 'Hãy nạp job ở máy này trước.' },
    { key: 'write', title: 'Bắt đầu và viết', done: started, why: sim ? (loaded ? '' : 'Hãy nạp job trước.') : 'Hãy ghi kết quả mô phỏng đạt trước.' },
    { key: 'finish', title: 'Viết xong', done: finished, why: st === 'WRITING' || finished ? '' : 'Chỉ khi job đang viết.' },
    { key: 'photos', title: 'Ảnh, QC và gửi khách', done: st === 'PHOTO_UPLOADED' || st === 'DONE', why: finished ? '' : 'Chỉ khi đã viết xong.' },
  ];
}

function modeSelect(key = 'mode', label = 'Chế độ chạy') {
  const modes = (S.agent && S.agent.modes) || [];
  return `<label class="row">${label} <select data-f="${key}">${modes.map((m) => `<option value="${m}" ${val(key) === m ? 'selected' : ''}>${esc(MODE[m] || m)}</option>`).join('')}</select></label>`;
}
const btn = (act, text, { tone = '', disabled = false, extra = '' } = {}) =>
  `<button type="button" class="${tone}" data-act="${act}" ${extra} ${disabled || S.busy ? 'disabled' : ''}>${esc(text)}</button>`;

function stepBody(k, d) {
  const id = d.id, mode = val('mode');
  switch (k) {
    case 'package': {
      const p = S.pkg[id];
      return `<p class="hint">Tải quỹ đạo đã duyệt và kiểm SHA-256 trên máy này trước khi chuẩn bị. Tải lại nếu link hết hạn.</p>
        <div class="row">${btn('package', p && p.ok ? 'Tải và kiểm lại' : 'Tải và kiểm hash', { tone: p && p.ok ? '' : 'go' })}</div>
        ${p ? `<div class="result ${p.ok ? 'okt' : 'err'}">${p.ok ? 'Hash khớp' : 'Hash KHÔNG khớp'}: <span class="mono">${esc(p.hash)}</span>
          ${p.info ? `\n${p.info.snapshot ? 'Gói đã ký (vật tư đã khoá).' : 'Gói cũ: chỉ có hash.'}${(p.info.material_drift || []).length ? '\nVật tư đã đổi sau khi khoá:\n• ' + p.info.material_drift.map(esc).join('\n• ') : ''}` : ''}</div>` : ''}`;
    }
    case 'robot': {
      const rs = (S.robots && S.robots.robots) || [];
      if (d.status !== 'SCHEDULED') return `<p>Robot: <b>${esc(robotLabel(d.robot_id))}</b>. Chỉ đổi được khi job đang ở trạng thái Đã xếp lịch.</p>`;
      const def = d.robot_id ?? (rs.some((r) => r.robot_id === localRobotId()) ? localRobotId() : null);
      const pick = Number(val('robotpick', def ?? '')) || null;
      const chosen = rs.find((r) => r.robot_id === pick);
      return `<p class="hint">Chỉ liệt kê robot quản lý đã giao cho bạn. Robot bảo trì hoặc hỏng không chọn được. Mặc định là robot của máy này.</p>
        <div class="stack">${rs.map((r) => `<label class="chk"><input type="radio" name="robotpick" data-f="robotpick" value="${r.robot_id}" ${pick === r.robot_id ? 'checked' : ''} ${OUT[r.robot_status] ? 'disabled' : ''}>
          <b>${esc(r.robot_code)}</b> ${r.robot_id === localRobotId() ? pill('máy này', 'ink plain') : ''} ${pill(LINK[r.connection_state] || LINK.UNKNOWN, linkTone(r.connection_state))}
          ${OUT[r.robot_status] ? pill(OUT[r.robot_status], 'warn') : ''} <span class="hint">${(r.supported_pen_categories || []).length ? 'Bút: ' + esc(r.supported_pen_categories.join(', ')) : ''}</span></label>`).join('') || '<p class="hint">Bạn chưa được giao robot nào.</p>'}</div>
        ${chosen && chosen.connection_state !== 'ONLINE' ? `<p class="warnt">${esc(chosen.robot_code)} đang không kết nối. Vẫn chọn được, nhưng agent của robot phải chạy trước khi nạp job.</p>` : ''}
        <div class="row" style="margin-top:8px">${btn('chooseRobot', d.robot_id == null ? 'Chọn robot này' : 'Đổi robot', { tone: 'go', disabled: !pick || pick === d.robot_id })}</div>`;
    }
    case 'prepare':
      return `<p class="hint">Ghi nhận chuẩn bị: gói đã kiểm, robot đã chọn.</p><div class="row">${btn('prepare', 'Bắt đầu chuẩn bị', { tone: 'go', disabled: d.status !== 'SCHEDULED' })}</div>`;
    case 'calibrate': {
      const tab = val('calTab', 'robot');
      const head = `<div class="warnbox" style="border-color:var(--warn);color:var(--warn)">Gửi hiệu chuẩn mới xoá kết quả mô phỏng cũ: phải làm lại bước 5 đến 8.</div>
        <div class="row" style="margin-top:8px">${btn('calTab', 'Đo bằng robot', { tone: tab === 'robot' ? 'go' : '', extra: 'data-v="robot"' })}${btn('calTab', 'Chọn file calibration.json', { tone: tab === 'file' ? 'go' : '', extra: 'data-v="file"' })}</div>`;
      if (tab === 'file') {
        return head + `<p class="hint">Chọn robot_agent/calibration.json. Ghi chú (khoá bắt đầu bằng _) được bỏ qua; ô chưa đo (null hoặc &lt;…&gt;) bị từ chối.</p>
          <div class="row"><input type="file" accept=".json,application/json" data-change="calFile" aria-label="File hiệu chuẩn">${btn('calSendFile', 'Gửi hiệu chuẩn', { tone: 'go', disabled: !S.calFile })}</div>
          ${S.calFileErr ? `<p class="err">${esc(S.calFileErr)}</p>` : S.calFile ? `<p class="okt">${esc(S.calFile.name)}: ${S.calFile.body.probe_points.length} điểm dò, sẵn sàng.</p>` : ''}`;
      }
      return head + `<p class="hint">Đưa đầu bút tới từng góc giấy rồi bấm "Lấy P…" (đọc vị trí robot, không di chuyển).</p>
        <div class="row">${modeSelect('mode', 'Đọc robot ở chế độ')}</div>
        <div class="stack" style="margin-top:8px">${CHECKLIST.map(([k, t]) => `<label class="chk"><input type="checkbox" data-f="chk_${k}" ${checked('chk_' + k)}> ${t}</label>`).join('')}</div>
        <label class="row" style="margin-top:8px">Độ lệch zero lực (N) <input data-f="offset" inputmode="decimal" value="${esc(val('offset'))}" style="width:120px"></label>
        <div class="points" style="margin-top:8px">${[0, 1, 2].map((i) => `<div class="point"><b>P${i}</b>${['x', 'y', 'z'].map((a) =>
          `<input data-f="p${i}${a}" inputmode="decimal" placeholder="${a} (mm)" aria-label="P${i} ${a}" value="${esc(val('p' + i + a))}">`).join('')}
          ${btn('probe', 'Lấy P' + i, { extra: `data-i="${i}"` })}</div>`).join('')}</div>
        <div class="row" style="margin-top:10px">${btn('calSend', 'Gửi hiệu chuẩn', { tone: 'go' })}</div>`;
    }
    case 'load': {
      const l = S.loaded[id];
      return `<p class="hint">Agent tải gói, kiểm hash, kiểm kế hoạch theo hiệu chuẩn và trả mã xác nhận của kế hoạch (giữ trong trang này).</p>
        <div class="row">${btn('load', l ? 'Nạp lại' : 'Nạp job', { tone: l ? '' : 'go' })}</div>
        ${l ? `<div class="result">${l.validation && l.validation.passed === false ? '<span class="err">Kế hoạch KHÔNG đạt.</span>\n' : '<span class="okt">Đã nạp.</span> '}${l.pages} trang · ${l.strokes} nét · bút ${esc(l.pen)}${l.estimated_seconds ? ' · ước ' + Math.round(l.estimated_seconds / 60) + ' phút' : ''}
Mã xác nhận: <span class="mono">${esc(String(l.authorization_token).slice(0, 18))}…</span></div>` : ''}`;
    }
    case 'preflight': {
      const p = S.pre[id];
      return `<div class="row">${modeSelect()}${btn('preflight', 'Kiểm tra trước', { tone: 'go' })}</div>
        <p class="hint">Kiểm tra kế hoạch và robot, không di chuyển.</p>
        ${p ? `<div class="result ${p.ok ? 'okt' : 'err'}">${p.ok ? 'Đạt' + (p.moves ? ` (${p.moves} chuyển động)` : '') + (p.note ? '. ' + esc(p.note) : '') : 'Không đạt: ' + esc(p.code || '') + ' ' + esc(p.message || '')}</div>` : ''}`;
    }
    case 'simulate':
      return `<p class="hint">Ghi kết quả mô phỏng: máy chủ kiểm lại kế hoạch và có thể đánh dấu không đạt (như <span class="mono">robot_console.py simulate</span>).</p>
        <div class="row">${btn('simulate', 'Ghi kết quả mô phỏng', { tone: 'go' })}</div>
        ${d.simulation_passed != null ? `<p class="${d.simulation_passed ? 'okt' : 'err'}">${d.simulation_passed ? 'Mô phỏng đạt.' : 'Mô phỏng không đạt.'} Có thể bắt đầu: ${d.can_start ? 'có' : 'chưa'}.</p>` : ''}`;
    case 'dryRun': {
      const last = (S.agent && S.agent.last) || null, mine = last && last.job_id === id && last.dry_run;
      return `<p class="hint">Bút nhấc, robot đi hết quỹ đạo. Chạy thử REAL cần <b>Bật REAL trước</b> (bước 9). Thứ tự đề xuất: Bật REAL → chạy thử REAL → viết REAL.</p>
        <div class="row">${modeSelect()}${btn('dryRun', 'Chạy thử nhấc bút', { tone: 'go', disabled: !!(S.agent && S.agent.busy) })}</div>
        ${mine ? `<p class="${last.result && last.result.state === 'DRY_RUN_DONE' ? 'okt' : 'err'}">Lần chạy thử gần nhất (${esc((last.mode || '').toUpperCase())}): ${esc((last.result && last.result.state) || (last.refused && last.refused.code) || last.error || '—')}</p>` : ''}`;
    }
    case 'real': {
      const a = S.agent || {}, on = a.real_enabled && a.real_enabled.job_id === id;
      if (!(a.modes || []).includes('real')) return '<p class="hint">Agent của máy này không có chế độ REAL (agent.json): máy không nối robot thật, nút bị ẩn.</p>';
      if (on) return `<p class="err"><b>REAL đang bật cho job này tới ${fmt(a.real_enabled.expires_at)}.</b>${a.real_enabled.waive_dry_run ? ' Đã BỎ chạy thử nhấc bút.' : ''}</p>
        <div class="row">${btn('realOff', 'Tắt REAL', { tone: 'danger' })}</div>`;
      const rc = S.realCheck && S.realCheck.job === id ? S.realCheck : null;
      return `<p class="hint">Chỉ cho job đã nạp ở máy này. Vẫn cần mã xác nhận của kế hoạch và một lần chạy thử REAL đạt (trừ khi bỏ chạy thử).</p>
        <p class="hint">Bấm "Bật REAL": máy kiểm tra kết nối tới robot thật trước (chỉ đọc, robot không chuyển động). Robot không phản hồi thì REAL <b>không</b> bật.</p>
        ${rc ? `<p class="err">Lần kiểm tra lúc ${fmt(rc.at)}: ${rc.code === 'ROBOT_CONFIG_MISMATCH' ? 'robot có trả lời nhưng cấu hình chưa khớp' : 'robot không phản hồi'}, REAL chưa bật. ${esc(rc.msg)}</p>` : ''}
        <div class="row"><label class="row">Số phút <input data-f="realmin" type="number" min="1" max="${a.max_minutes || 120}" value="${esc(val('realmin', '30'))}" style="width:90px"></label>
        <label class="chk"><input type="checkbox" data-f="waive" ${checked('waive')}> Bỏ chạy thử nhấc bút</label></div>
        ${S.f.waive ? '<div class="warnbox" style="margin-top:8px">Bỏ chạy thử: bút chạm giấy ngay nét đầu, không có lần đi thử trên robot thật. Đứng sẵn ở nút E-Stop.</div>' : ''}
        <div class="row" style="margin-top:8px">${btn('realOn', 'Bật REAL', { tone: 'danger' })}</div>`;
    }
    case 'write': {
      const running = !!(S.agent && S.agent.busy);
      return `<div class="row">${modeSelect()}</div>
        <div class="row" style="margin-top:8px"><label class="row">Viết tiếp từ nét <input data-f="resume" type="number" min="0" value="${esc(val('resume'))}" style="width:100px" placeholder="tự động"></label>
          <label class="chk"><input type="checkbox" data-f="unknown" ${checked('unknown')}> Tôi đã xem tờ giấy (lần trước kết thúc không rõ)</label></div>
        ${mode === 'real' ? '<div class="warnbox" style="margin-top:8px">Robot THẬT: đứng cạnh nút E-Stop, vùng robot trống, giấy kẹp chặt.</div>' : ''}
        <div class="row" style="margin-top:8px">${btn('write', d.status === 'PREPARING' ? 'Bắt đầu và viết' : 'Viết tiếp', { tone: 'go', disabled: running })}</div>
        ${running ? '<p class="hint">Robot đang chạy: dùng thanh điều khiển ở cuối màn hình.</p>' : ''}`;
    }
    case 'finish':
      return `<p class="hint">Ghi nhận viết xong khi robot đã hoàn tất đủ số bản của đơn.</p>${copiesNote(d)}${orphanNote(d)}<div class="row">${btn('finish', 'Viết xong', { tone: 'go', disabled: d.status !== 'WRITING' || copiesLeft(d) > 0 })}</div>`;
    case 'photos': return photosBody(d);
    default: return '';
  }
}

function photosBody(d) {
  const id = d.id, ps = S.photos[id];
  const canEdit = d.status === 'WRITTEN';
  if (!ps) return '<p class="hint">Đang tải ảnh…</p>';
  const ready = ps.length >= 2 && ps.length <= 10 && ['OVERALL', 'CLOSE_UP'].every((k) => ps.some((p) => p.kind === k)) && ps.every((p) => p.qc_result === 'PASS');
  const q = S.quality[id] || {};
  return `<p class="hint">Cần ít nhất một ảnh toàn cảnh và một ảnh cận cảnh (tối đa 10), mọi ảnh đạt QC, rồi gửi khách.</p>
    ${canEdit ? `<div class="row"><select data-f="pkind" aria-label="Loại ảnh">${[['OVERALL', 'Toàn cảnh'], ['CLOSE_UP', 'Cận cảnh'], ['OTHER', 'Khác']].map(([v, t]) => `<option value="${v}" ${val('pkind', 'OVERALL') === v ? 'selected' : ''}>${t}</option>`).join('')}</select>
      <input type="file" accept="image/jpeg,image/png,image/webp" data-change="upload" aria-label="Tải ảnh lên" ${S.busy ? 'disabled' : ''}></div>` : ''}
    <div class="photos" style="margin-top:10px">${ps.map((p) => `<div class="photo">
      ${p.url ? `<img src="${esc(p.url)}" alt="Ảnh ${esc(p.kind)} của job ${id}">` : '<div class="hint">Không có link ảnh</div>'}
      <div class="row" style="margin-top:6px;justify-content:space-between"><b>${p.kind === 'OVERALL' ? 'Toàn cảnh' : p.kind === 'CLOSE_UP' ? 'Cận cảnh' : 'Khác'}</b>
        ${p.qc_result ? pill(p.qc_result === 'PASS' ? 'Đạt' : 'Không đạt', p.qc_result === 'PASS' ? 'ok' : 'bad') : pill('Chưa QC')}</div>
      ${q[p.id] ? `<div class="hint">Đánh giá: ${esc(q[p.id].verdict)}${q[p.id].advisory ? ' · ' + esc(q[p.id].advisory) : ''}</div>` : ''}
      ${canEdit ? `<input data-f="qcnote${p.id}" placeholder="Ghi chú QC" aria-label="Ghi chú QC" value="${esc(val('qcnote' + p.id))}" style="width:100%;margin-top:6px">
        <div class="row" style="margin-top:6px">${btn('qc', 'Đạt', { extra: `data-id="${p.id}" data-v="PASS"` })}${btn('qc', 'Không đạt', { extra: `data-id="${p.id}" data-v="FAIL"` })}
        ${btn('evaluate', 'Đánh giá', { extra: `data-id="${p.id}"` })}${btn('delPhoto', 'Xoá', { extra: `data-id="${p.id}"` })}</div>` : ''}
    </div>`).join('')}</div>
    ${canEdit ? `<div class="row" style="margin-top:10px">${btn('submitPhotos', 'Gửi ảnh cho khách', { tone: 'go', disabled: !ready })}</div>
      <details style="margin-top:10px"><summary>QC không đạt: viết lại</summary>
        <textarea data-f="qcfail" placeholder="Lý do (bắt buộc)" aria-label="Lý do QC không đạt">${esc(val('qcfail'))}</textarea>
        <div class="row">${btn('qcFail', 'Báo QC không đạt', { tone: 'danger' })}</div></details>` : ''}`;
}

function toolsBody(d) {
  const live = ['PREPARING', 'WRITING', 'PAUSED'].includes(d.status);
  if (!live && !S.loaded[d.id]) return '';
  return `<section class="card" style="margin-top:12px" aria-label="Công cụ">
    <h2>Công cụ</h2>
    <div class="row" style="margin-top:8px">${btn('home', 'Về điểm chờ')}${btn('log', 'Nhật ký chạy')}</div>
    <details style="margin-top:10px"><summary>Viết lại từ đầu (tờ mới)</summary>
      <label class="chk"><input type="checkbox" data-f="newsheet" ${checked('newsheet')}> Tờ giấy là tờ MỚI, trắng, kẹp đúng vị trí cũ</label>
      <div class="row">${btn('resetProgress', 'Đặt lại tiến độ', { disabled: !S.f.newsheet })}</div></details>
    ${live ? `<details style="margin-top:10px"><summary>Báo sự cố</summary>
      <div class="row" style="margin-top:6px"><select data-f="itype" aria-label="Loại sự cố">${[['ROBOT', 'Robot'], ['MATERIAL', 'Vật tư'], ['FORCE_MODULE', 'Module lực'], ['OTHER', 'Khác']].map(([v, t]) => `<option value="${v}" ${val('itype', 'OTHER') === v ? 'selected' : ''}>${t}</option>`).join('')}</select>
        <select data-f="iafter" aria-label="Trạng thái robot sau sự cố"><option value="">Giữ trạng thái robot</option><option value="MAINTENANCE" ${val('iafter') === 'MAINTENANCE' ? 'selected' : ''}>Chuyển sang bảo trì</option><option value="BROKEN" ${val('iafter') === 'BROKEN' ? 'selected' : ''}>Đánh dấu hỏng</option></select></div>
      <textarea data-f="idesc" placeholder="Mô tả (bắt buộc)" aria-label="Mô tả sự cố" style="margin-top:6px">${esc(val('idesc'))}</textarea>
      <div class="row">${btn('incident', 'Gửi sự cố', { tone: 'danger' })}</div>
      <p class="hint">Sự cố xác nhận sẽ đánh dấu job Thất bại và trả đơn về quản lý.</p></details>` : ''}
    ${S.log ? `<pre class="log">${esc(S.log)}</pre>` : ''}
  </section>`;
}

function signature(d) {
  const a = S.agent || {};
  return JSON.stringify([d && [d.id, d.status, d.robot_id, d.calibration && d.calibration.id, d.calibration && d.calibration.is_valid, d.simulation_passed, d.downloaded_at, d.can_start, d.copies_written, d.open_run && [d.open_run.run_id, d.open_run.orphan]],
    S.open, S.busy, S.f.calTab, S.f.waive, S.f.newsheet, S.f.mode, Object.keys(S.loaded), S.pre[S.sel], S.pkg[S.sel], S.photos[S.sel], S.quality[S.sel], S.calFile && S.calFile.name, S.calFileErr, S.log,
    a.busy, a.last && [a.last.job_id, a.last.dry_run, a.last.result && a.last.result.state], a.real_enabled && [a.real_enabled.job_id, a.real_enabled.expires_at], (a.modes || []).join(),
    S.robots && S.robots.robots.map((r) => [r.robot_id, r.connection_state, r.robot_status]), S.detailErr]);
}

function renderDetail(force = false) {
  const d = S.detail;
  const sig = signature(d);
  if (!force && sig === S.sig) { updateMeter(); return; }
  S.sig = sig;
  const box = $('detail');
  if (!S.sel) { box.innerHTML = '<h2>Chọn một job</h2><p class="hint">Chọn job ở cột trái để xem các bước và nút điều khiển.</p>'; return; }
  if (!d) { box.innerHTML = S.detailErr ? `<p class="err">${esc(S.detailErr)}</p>` : '<p class="hint">Đang tải job…</p>'; return; }
  const list = steps(d);
  const current = list.findIndex((s) => !s.done && !s.optional && !s.why);
  if (S.open == null || (S.open !== '' && !list.some((s) => s.key === S.open))) S.open = (list[current] || list[list.length - 1]).key;
  // The open step just got done (by an action here or on another screen): move on to the step that is now current.
  const openStep = list.find((s) => s.key === S.open);
  if (openStep && openStep.done && S.openPending === S.open && list[current]) S.open = list[current].key;
  const nowOpen = list.find((s) => s.key === S.open);
  S.openPending = nowOpen && !nowOpen.done ? S.open : null;
  const dead = ['CANCELLED', 'FAILED', 'REWRITE_REQUIRED'].includes(d.status);
  box.innerHTML = `
    <div class="row" style="justify-content:space-between"><div class="row"><h2 style="margin:0;font-size:22px">${esc(d.order_code || '#' + d.order_id)}</h2>${pill(JOB_STATUS[d.status] || d.status, jobTone(d.status))}</div>
      <span class="hint">Job #${d.id}${d.is_rewrite ? ' · viết lại' : ''}${(d.quantity || 1) > 1 ? ` · bản ${Math.min(d.copies_written || 0, d.quantity)}/${d.quantity}` : ''}</span></div>
    <div class="facts">
      <div class="fact"><span>Robot</span><b>${esc(robotLabel(d.robot_id))}</b></div>
      <div class="fact"><span>Bắt đầu theo lịch</span><b>${esc(fmt(d.slot_start))}</b></div>
      <div class="fact"><span>Kết thúc theo lịch</span><b>${esc(fmt(d.slot_end))}</b></div>
      <div class="fact"><span>Giấy · Bút · Mực</span><b>${esc([d.paper_name, d.pen_name, d.ink_name].filter(Boolean).join(' · ') || '—')}</b></div>
    </div>
    ${d.approach_note ? `<p class="hint">${esc(d.approach_note)}</p>` : ''}
    <div class="meter" aria-label="Tiến độ"><i id="meter" style="width:${Math.max(0, Math.min(100, d.progress_pct || 0))}%"></i></div>
    ${dead ? `<p class="err">Job ${esc(JOB_STATUS[d.status])}: không còn bước nào để làm.</p>` : ''}
    <ol class="steps">${list.map((s, i) => {
      const state = s.done ? 'done' : (!dead && i === current) ? 'current' : s.why ? 'locked' : 'todo';
      const open = !dead && S.open === s.key;
      return `<li class="step ${state}"><button type="button" class="sh" data-act="step" data-k="${s.key}" aria-expanded="${open}" ${state === 'current' ? 'aria-current="step"' : ''}>
          <span class="num">${s.done ? '✓' : s.why ? '🔒︎' : i + 1}</span>
          <span><span class="t">${i + 1}. ${esc(s.title)}</span>${s.why && !s.done ? `<span class="why">${esc(s.why)}</span>` : ''}</span>
          <span class="hint">${s.done ? 'xong' : s.optional ? 'tuỳ chọn' : ''}</span></button>
        ${open ? `<div class="sb"><div class="panel">${stepBody(s.key, d)}</div></div>` : ''}</li>`;
    }).join('')}</ol>
    ${toolsBody(d)}`;
  if (S.open === 'photos' && !S.photos[d.id] && AFTER_FINISH.includes(d.status)) loadPhotos(d.id);
}
// One robot run writes one copy. The server counts the runs that ended DONE and refuses "Viết xong" below the order's quantity.
// A run the server still holds open although this workstation is not running anything (its "run closed" message was lost).
// It blocks the next run (ROBOT_BUSY) and "Viết xong" (RUN_OPEN) until someone closes it, with a reason.
function orphanNote(d) {
  const r = d.open_run;
  if (!r) return '';
  if (!r.orphan || (S.agent && S.agent.busy)) return `<p class="hint">Robot đang có một lần chạy mở trên máy chủ (${esc(r.run_id)}).</p>`;
  return `<p class="err">Máy chủ còn giữ lần chạy ${esc(r.run_id)} đang mở, nhưng máy trạm không chạy gì (mất kết nối lúc kết thúc). Kiểm tra tờ giấy và robot, rồi đóng lần chạy này để làm tiếp.</p>
    <textarea data-f="orphanwhy" placeholder="Lý do (ít nhất 10 ký tự), ví dụ: robot đã dừng, mất mạng lúc viết xong" aria-label="Lý do đóng lần chạy" style="margin-top:6px">${esc(val('orphanwhy'))}</textarea>
    <div class="row">${btn('closeOrphan', 'Đóng lần chạy treo')}</div>`;
}
function copiesLeft(d) { return Math.max(0, (d.quantity || 1) - (d.copies_written || 0)); }
function copiesNote(d) {
  const n = d.quantity || 1, k = d.copies_written || 0;
  if (n <= 1 && k <= 1) return '';
  const next = k < n && k > 0 ? ' Để viết bản tiếp theo: đặt tờ giấy mới, mở "Đặt lại tiến độ" ở bước chạy robot và xác nhận giấy mới, rồi chạy lại.' : '';
  return `<p class="${k >= n ? 'okt' : 'err'}">Robot đã viết xong ${k}/${n} bản.${next}</p>`;
}
function updateMeter() { const m = $('meter'); if (m && S.detail) m.style.width = Math.max(0, Math.min(100, S.detail.progress_pct || 0)) + '%'; }

// ─── Loading ─────────────────────────────────────────────────────────
async function loadRobots() {
  try { S.robots = await tech('robots'); S.robotsErr = ''; } catch (e) { S.robotsErr = errText(e); if (e.status === 403) noWorkspace(); }
  renderStrip(); renderHeader(); renderEstop(); renderDetail();
}
async function loadJobs() {
  try {
    const items = [];
    for (let page = 1; page < 20; page++) {
      const r = await tech(`jobs?page=${page}&page_size=200`);
      items.push(...r.items);
      if (!r.items.length || page * r.page_size >= r.total) break;
    }
    S.jobs = items; S.jobsErr = '';
  } catch (e) { S.jobsErr = errText(e); }
  renderJobs();
}
async function loadDetail() {
  if (!S.sel) { S.detail = null; renderDetail(true); return; }
  try { S.detail = await tech('jobs/' + S.sel); S.detailErr = ''; } catch (e) { S.detail = null; S.detailErr = errText(e); }
  renderDetail();
}
async function loadAgentJob(id) {
  try { const r = await api('/api/jobs/' + id); S.loaded[id] = r; } catch (e) { /* not loaded here: fine */ }
}
async function loadPhotos(id) {
  try { S.photos[id] = await tech(`jobs/${id}/photos`); } catch (e) { S.photos[id] = []; toast(errText(e), true); }
  renderDetail();
}
async function refreshJob() { await Promise.all([loadDetail(), loadJobs()]); }

async function selectJob(id) {
  if (S.sel !== id) { S.open = null; S.log = null; S.calFile = null; S.calFileErr = ''; }
  S.sel = id; S.detail = null; S.detailErr = '';
  const u = new URL(location.href); u.searchParams.set('job', id); history.replaceState(null, '', u);
  renderJobs(); renderDetail(true);
  await loadAgentJob(id);
  await loadDetail();
}

// ─── Actions ─────────────────────────────────────────────────────────
async function act(fn, { confirm: question, ok } = {}) {
  if (S.busy) return;
  if (question && !window.confirm(question)) return;
  S.busy = true; renderDetail(true);
  try { const r = await fn(); if (ok) toast(ok); return r; } catch (e) { toast(errText(e), true); }
  finally { S.busy = false; await refreshJob(); renderDetail(true); }
}
const num = (k) => { const v = parseFloat(String(S.f[k] ?? '').replace(',', '.')); return Number.isFinite(v) ? v : NaN; };
const authFor = (id, mode) => (mode === 'real' && S.loaded[id] ? { authorization: S.loaded[id].authorization_token } : {});

const ACTIONS = {
  step: (el) => { S.open = S.open === el.dataset.k ? '' : el.dataset.k; renderDetail(true); },
  open: (el) => selectJob(Number(el.dataset.id)),
  filter: (el) => { const id = Number(el.dataset.id); S.robotFilter = S.robotFilter === id ? null : id; renderStrip(); renderJobs(); },
  rcmd: (el) => {
    const kind = el.dataset.kind, rid = Number(el.dataset.id);
    act(() => robotCommand(kind, { robot_id: rid }, {}, 30), { confirm: kind === 'STOP' ? `DỪNG robot ${robotLabel(rid)}?` : null, ok: `Đã gửi lệnh ${kind === 'STOP' ? 'DỪNG' : 'Tạm dừng'} tới ${robotLabel(rid)}.` });
  },
  calTab: (el) => { S.f.calTab = el.dataset.v; renderDetail(true); },
  package: () => act(async () => {
    const id = S.sel, info = await tech(`jobs/${id}/package`);
    const res = await fetch(info.trajectory_url, { credentials: 'omit' }).catch(() => null);
    if (!res || !res.ok) throw new ApiErr(res ? res.status : 0, 'STORAGE_DOWNLOAD_FAILED', 'Không tải được file quỹ đạo (link có thể đã hết hạn): bấm tải lại.');
    const hash = await sha256hex(new Uint8Array(await res.arrayBuffer()));
    const ok = hash === String(info.package_hash).toLowerCase();
    S.pkg[id] = { ok, hash, info };
    if (!ok) throw new ApiErr(409, 'JOB_HASH_MISMATCH', '');
  }, { ok: 'Gói đã tải và hash khớp.' }),
  chooseRobot: () => act(() => tech(`jobs/${S.sel}/robot`, { method: 'PUT', body: { robot_id: Number(S.f.robotpick || S.detail.robot_id || localRobotId()) } }), { ok: 'Đã chọn robot.' }),
  prepare: () => act(() => tech(`jobs/${S.sel}/prepare`, { method: 'POST' }), { ok: 'Đã ghi nhận chuẩn bị.' }),
  probe: (el) => act(async () => {
    const i = el.dataset.i, r = await api('/api/robot/identify', { method: 'POST', body: { mode: S.f.mode } });
    ['x', 'y', 'z'].forEach((a, k) => { S.f[`p${i}${a}`] = String(r.tcp_mm[k]); });
  }, { ok: 'Đã lấy vị trí đầu bút.' }),
  calSend: () => {
    const points = [0, 1, 2].map((i) => ({ x: num(`p${i}x`), y: num(`p${i}y`), z: num(`p${i}z`) }));
    const offset = num('offset');
    if (!CHECKLIST.every(([k]) => S.f['chk_' + k])) return toast('Hãy đánh dấu đủ bốn mục checklist.', true);
    if (!Number.isFinite(offset) || points.some((p) => ![p.x, p.y, p.z].every(Number.isFinite))) return toast('Hãy nhập số vào mọi ô (độ lệch zero lực và P0 đến P2).', true);
    if (!planeOk(points)) return toast('P0, P1, P2 thẳng hàng hoặc trùng nhau: không xác định được mặt giấy.', true);
    sendCalibration({ checklist: Object.fromEntries(CHECKLIST.map(([k]) => [k, true])), force_zero_offset: offset, probe_points: points });
  },
  calSendFile: () => S.calFile && sendCalibration(S.calFile.body),
  load: () => act(async () => { S.loaded[S.sel] = await api(`/api/jobs/${S.sel}/load`, { method: 'POST' }); delete S.pre[S.sel]; }, { ok: 'Đã nạp job vào máy này.' }),
  preflight: () => act(async () => { S.pre[S.sel] = await api(`/api/jobs/${S.sel}/preflight`, { method: 'POST', body: { mode: S.f.mode } }); }),
  simulate: () => act(() => tech(`jobs/${S.sel}/simulation`, { method: 'POST', body: { passed: true } }), { ok: 'Đã ghi kết quả mô phỏng.' }),
  dryRun: () => act(() => api(`/api/jobs/${S.sel}/dry-run`, { method: 'POST', body: { mode: S.f.mode, ...authFor(S.sel, S.f.mode) } }),
    { confirm: S.f.mode === 'real' ? 'Chạy thử trên robot THẬT (bút nhấc)? Đứng cạnh nút E-Stop, vùng robot trống.' : null, ok: 'Đã bắt đầu chạy thử.' }),
  realOn: () => {
    const minutes = parseInt(S.f.realmin, 10), id = S.sel;
    act(async () => {
      toast('Đang kiểm tra kết nối tới robot thật…');
      try {
        const r = await api(`/api/jobs/${id}/real-enable`, { method: 'POST', body: { minutes, ...(S.f.waive ? { waive_dry_run: true, confirm_waive: 'SKIP-DRY-RUN' } : {}) } });
        S.realCheck = null;
        const c = (r && r.robot_check) || {}, v = (c.controller && c.controller.controller_version) || '';
        toast(`Robot phản hồi${v ? ' (controller ' + v + ')' : ''}: REAL đã bật cho job này.`);
        return r;
      } catch (e) {
        if (e && (e.code === 'ROBOT_UNREACHABLE' || e.code === 'ROBOT_CONFIG_MISMATCH')) S.realCheck = { job: id, at: Date.now() / 1000, code: e.code, msg: e.message || '' };
        throw e;
      }
    }, { confirm: S.f.waive ? `Bật REAL ${minutes} phút và BỎ chạy thử nhấc bút? Bút chạm giấy ngay nét đầu.` : `Bật REAL cho job ${id} trong ${minutes} phút?` });
  },
  realOff: () => act(() => api('/api/real-enable', { method: 'DELETE' }), { ok: 'Đã tắt REAL.' }),
  write: () => {
    const id = S.sel, mode = S.f.mode, d = S.detail;
    act(async () => {
      if (d.status === 'PREPARING') await tech(`jobs/${id}/start`, { method: 'POST' });
      const body = { mode, ...authFor(id, mode) };
      if (S.f.resume !== undefined && String(S.f.resume).trim() !== '') body.resume_from = parseInt(S.f.resume, 10);
      if (S.f.unknown) body.confirm_unknown = true;
      return api(`/api/jobs/${id}/run`, { method: 'POST', body });
    }, { confirm: mode === 'real' ? 'Chạy robot THẬT? Bạn phải đứng cạnh nút E-Stop, vùng robot trống và giấy đã kẹp chặt.' : null, ok: 'Robot bắt đầu viết.' });
  },
  finish: () => act(() => tech(`jobs/${S.sel}/finish`, { method: 'POST' }), { confirm: 'Ghi nhận job đã viết xong?', ok: 'Đã ghi nhận viết xong.' }),
  qc: (el) => act(async () => {
    const id = S.sel, pid = el.dataset.id;
    await tech(`jobs/${id}/photos/${pid}`, { method: 'PATCH', body: { qc_result: el.dataset.v, qc_note: (S.f['qcnote' + pid] || '').trim() || null } });
    delete S.photos[id];
  }),
  evaluate: (el) => act(async () => {
    const id = S.sel, r = await tech(`jobs/${id}/photos/${el.dataset.id}/evaluate`, { method: 'POST', body: { page: 1 } });
    S.quality[id] = { ...(S.quality[id] || {}), [el.dataset.id]: r };
  }),
  delPhoto: (el) => act(async () => { await tech(`jobs/${S.sel}/photos/${el.dataset.id}`, { method: 'DELETE' }); delete S.photos[S.sel]; }, { confirm: 'Xoá ảnh này?' }),
  submitPhotos: () => act(() => tech(`jobs/${S.sel}/photos/submit`, { method: 'POST' }), { confirm: 'Gửi ảnh cho khách?', ok: 'Đã gửi ảnh cho khách.' }),
  qcFail: () => {
    const note = (S.f.qcfail || '').trim();
    if (!note) return toast('Hãy nhập lý do QC không đạt.', true);
    act(() => tech(`jobs/${S.sel}/qc-fail`, { method: 'POST', body: { note } }), { confirm: 'Báo QC không đạt? Job sẽ phải viết lại.', ok: 'Đã báo QC không đạt.' });
  },
  home: () => {
    const id = S.sel, mode = S.f.mode;
    act(async () => {
      await robotCommand('STOP', { job_id: id }, {}, 30).catch((e) => { if (e.code !== 'NO_RUN_ACTIVE') throw e; });
      const end = Date.now() + 60000;
      while (Date.now() < end) { const a = await api('/api/agent'); if (!a.busy) break; await sleep(500); }
      await sleep(1000);
      return robotCommand('ALIGN_START', { job_id: id }, { mode, ...authFor(id, mode) }, 180);
    }, { confirm: `DỪNG rồi đưa bút về điểm chờ (${(mode || '').toUpperCase()})?`, ok: 'Bút đã về điểm chờ.' });
  },
  log: () => act(async () => {
    const r = await api(`/api/jobs/${S.sel}/log?tail=200`);
    S.log = r.lines.length ? r.file + '\n' + r.lines.map((x) => JSON.stringify(x)).join('\n') : 'Chưa có nhật ký chạy cho job này.';
  }),
  resetProgress: () => act(async () => {
    const r = await api(`/api/jobs/${S.sel}/reset-progress`, { method: 'POST', body: { confirm: 'NEW_SHEET' } });
    S.f.newsheet = false;
    toast(r.reset ? `Đã đặt lại tiến độ (sao lưu ${r.backup}).` : 'Job này chưa viết gì: không cần đặt lại.');
  }, { confirm: 'Lần chạy sau viết lại từ nét đầu. Tờ giấy là tờ MỚI, trắng?' }),
  closeOrphan: () => {
    const reason = (S.f.orphanwhy || '').trim(), run = S.detail && S.detail.open_run;
    if (!run) return toast('Không còn lần chạy nào đang mở.', true);
    if (reason.length < 10) return toast('Hãy ghi lý do (ít nhất 10 ký tự).', true);
    act(async () => { await tech(`runs/${encodeURIComponent(run.run_id)}/close-orphan`, { method: 'POST', body: { reason } }); S.f.orphanwhy = ''; },
      { confirm: 'Đóng lần chạy này với kết quả "không rõ"? Chỉ làm khi robot đã đứng yên.', ok: 'Đã đóng lần chạy.' });
  },
  incident: () => {
    const description = (S.f.idesc || '').trim();
    if (!description) return toast('Hãy mô tả sự cố.', true);
    const body = { type: S.f.itype || 'OTHER', description, ...(S.f.iafter ? { robot_status_after: S.f.iafter } : {}) };
    act(async () => { await tech(`jobs/${S.sel}/incidents`, { method: 'POST', body }); S.f.idesc = ''; }, { confirm: 'Gửi sự cố? Job sẽ bị đánh dấu Thất bại.', ok: 'Đã gửi sự cố.' });
  },
};

function sendCalibration(body) {
  const d = S.detail, again = d.calibration || d.simulation_passed != null;
  act(async () => {
    await tech(`jobs/${S.sel}/calibration`, { method: 'POST', body });
    delete S.loaded[S.sel]; delete S.pre[S.sel]; S.calFile = null;
  }, { confirm: again ? 'Hiệu chuẩn mới xoá kết quả mô phỏng cũ: phải làm lại Nạp, Kiểm tra trước, Mô phỏng và Chạy thử. Gửi?' : null, ok: 'Đã gửi hiệu chuẩn.' });
}

const CHANGES = {
  calFile: async (el) => {
    const file = el.files && el.files[0];
    if (!file) return;
    try { S.calFile = { name: file.name, body: readCalibrationFile(await file.text()) }; S.calFileErr = ''; }
    catch (e) { S.calFile = null; S.calFileErr = e.message; }
    renderDetail(true);
  },
  upload: (el) => {
    const file = el.files && el.files[0], id = S.sel;
    if (!file) return;
    act(async () => {
      const ticket = await tech(`jobs/${id}/photos/upload-url`, { method: 'POST', body: { mime_type: file.type, size_bytes: file.size } });
      const r = await fetch(ticket.upload_url, { method: ticket.method || 'PUT', headers: { 'Content-Type': file.type }, body: file, credentials: 'omit' }).catch(() => null);
      if (!r || !r.ok) throw new ApiErr(r ? r.status : 0, 'UPLOAD_FAILED', 'Không tải được ảnh lên kho lưu trữ: thử lại.');
      await tech(`jobs/${id}/photos`, { method: 'POST', body: { photo_key: ticket.photo_key, kind: S.f.pkind || 'OVERALL' } });
      delete S.photos[id];
    }, { ok: 'Đã thêm ảnh.' });
  },
};

document.addEventListener('click', (e) => {
  const el = e.target.closest('[data-act]');
  if (!el || el.disabled || !ACTIONS[el.dataset.act]) return;
  ACTIONS[el.dataset.act](el);
});
document.addEventListener('input', (e) => {
  const el = e.target;
  if (!el.dataset || !el.dataset.f) return;
  S.f[el.dataset.f] = el.type === 'checkbox' ? el.checked : el.value;
  if (['waive', 'newsheet', 'mode', 'robotpick'].includes(el.dataset.f)) renderDetail(true);
});
document.addEventListener('change', (e) => {
  const el = e.target;
  if (el.dataset && el.dataset.f && (el.type === 'radio' || el.tagName === 'SELECT')) { S.f[el.dataset.f] = el.value; renderDetail(true); }
  if (el.dataset && el.dataset.change && CHANGES[el.dataset.change]) CHANGES[el.dataset.change](el);
});

// ─── This machine's robot: live view, alerts, E-Stop, control bar ────
function toPaper(tcp) {
  const f = S.localJob.frame, o = f.origin, d = [tcp[0] - o[0], tcp[1] - o[1], tcp[2] - o[2]];
  const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  const u = dot(d, f.x_axis), v = dot(d, f.y_axis), h = dot(d, f.normal);
  const [a, b, c] = f.height_coeffs;
  return { u, v, lift: h - (a * u + b * v + c) };
}
function draw() {
  const job = S.localJob, snap = S.snap;
  if (!job || !job.pages || !job.pages.length) return;
  const pg = job.pages[0], cv = $('cv'), g = cv.getContext('2d');
  cv.hidden = false;                                                       // shown only once this machine has a job to draw
  const s = Math.min(700 / pg.width_mm, 990 / pg.height_mm);
  cv.height = Math.round(pg.height_mm * s); cv.width = Math.round(pg.width_mm * s);
  g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.strokeStyle = '#bbb'; g.strokeRect(0.5, 0.5, cv.width - 1, cv.height - 1);
  const done = snap ? snap.stroke : 0;
  pg.strokes.forEach((st, i) => {
    g.beginPath(); st.forEach((p, j) => (j ? g.lineTo(p[0] * s, p[1] * s) : g.moveTo(p[0] * s, p[1] * s)));
    g.strokeStyle = i < done ? '#1f4e79' : '#b9b7ae'; g.lineWidth = i < done ? 2 : 1.2; g.stroke();
  });
  if (snap && snap.tcp && job.frame) {
    const t = toPaper(snap.tcp), down = t.lift < 0.3;
    g.beginPath(); g.arc(t.u * s, t.v * s, down ? 6 : 9, 0, 6.3);
    g.fillStyle = down ? '#c62828' : 'rgba(31,78,121,.35)'; g.fill(); g.strokeStyle = '#000'; g.lineWidth = 1; g.stroke();
  }
}
let audio = null, siren = null;
$('sound').onclick = () => { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); $('sound').textContent = 'Âm thanh cảnh báo: bật'; };
function setSiren(on) {
  if (on && audio && !siren) {
    const o = audio.createOscillator(), g = audio.createGain();
    o.type = 'square'; o.frequency.value = 880; g.gain.value = 0.08; o.connect(g); g.connect(audio.destination); o.start();
    let hi = true; const t = setInterval(() => { o.frequency.value = hi ? 660 : 880; hi = !hi; }, 450);
    siren = { o, t };
  } else if (!on && siren) { siren.o.stop(); clearInterval(siren.t); siren = null; }
}
function renderEstop() {
  const red = (S.snap && S.snap.level >= 4) || ((S.robots && S.robots.robots) || []).some((r) => r.level >= 4);
  $('estop').hidden = !red;
  setSiren(red);
  document.title = (red ? 'E-STOP! ' : '') + 'VHRS · Máy trạm';
}
function renderAlerts() {
  const box = $('alerts'), list = (S.snap && S.snap.alerts) || [];
  box.innerHTML = list.map((a) => `<div class="al l${a.level}"><b>${esc(a.title_vi)}</b><div class="act">${esc(a.action_vi)}</div>
    ${a.source === 'local' ? '<small>Nội dung dự phòng tại máy trạm (chưa lấy được từ máy chủ).</small>' : ''}</div>`).join('');
}
function renderMonitor() {
  const snap = S.snap;
  if (!snap) return;
  window.vhrsSnap = snap;
  if (window.twin) window.twin.update(snap);
  renderAlerts(); renderEstop();
  $('state').textContent = snap.state; $('state').className = 'state ' + snap.state;
  $('mode').textContent = snap.mode || '—';
  $('localjob').textContent = snap.job_id != null ? '#' + snap.job_id : '—';
  $('msg').textContent = [snap.fault, snap.message].filter(Boolean).join(' · ');
  $('prog').textContent = (snap.progress_pct || 0).toFixed(1) + ' %';
  $('stroke').textContent = snap.stroke + ' / ' + snap.total_strokes; $('kind').textContent = snap.move_kind || '—';
  if (snap.tcp && S.localJob && S.localJob.frame) {
    const t = toPaper(snap.tcp); $('pos').textContent = t.u.toFixed(1) + ', ' + t.v.toFixed(1) + ' mm'; $('lift').textContent = t.lift.toFixed(2) + ' mm';
  }
  if (snap.force_n != null && S.localJob && S.localJob.limits) {
    const L = S.localJob.limits, top = L.f_hard * 1.1;
    $('force').textContent = snap.force_n.toFixed(2) + ' N (dải ' + L.f_min + '–' + L.f_max + ', tối đa ' + L.f_hard + ')';
    $('needle').style.left = Math.min(100, snap.force_n / top * 100) + '%';
    $('band').style.left = (L.f_min / top * 100) + '%'; $('band').style.width = ((L.f_max - L.f_min) / top * 100) + '%';
  } else $('force').textContent = '—';
  $('cb-state').textContent = snap.state + (snap.mode ? ' · ' + String(snap.mode).toUpperCase() : '');
  $('cb-detail').textContent = snap.job_id != null ? `Job #${snap.job_id} · ${(snap.progress_pct || 0).toFixed(0)}% · nét ${snap.stroke}/${snap.total_strokes}` : 'Robot của máy này chưa chạy job nào.';
  $('paper').hidden = snap.state !== 'AWAITING_PAPER';
  if (snap.job_id != null && (!S.localJob || S.localJob.job_id !== snap.job_id)) {
    S.localJob = { job_id: snap.job_id };
    api('/api/job').then((j) => { S.localJob = j; draw(); }).catch(() => {});
  }
  draw();
}
async function control(path, text) {
  try { await api('/api/' + path, { method: 'POST' }); toast(text); } catch (e) { toast('Lệnh bị từ chối: ' + errText(e), true); }
}
$('pause').onclick = () => control('pause', 'Đã tạm dừng.');
$('resume').onclick = () => control('resume', 'Đã tiếp tục.');
$('stop').onclick = () => control('stop', 'Đã DỪNG.');
$('paper').onclick = () => control('paper-changed', 'Đã xác nhận thay giấy.');

function connectWs() {
  const q = S.bearer ? '?token=' + encodeURIComponent(S.bearer) : (S.viewerToken ? '?token=' + encodeURIComponent(S.viewerToken) : '');
  const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws' + q);
  ws.onopen = () => { $('conn').textContent = 'đã kết nối agent'; $('conn').className = 'hint'; };
  ws.onclose = () => { $('conn').textContent = 'MẤT KẾT NỐI với agent'; $('conn').className = 'err'; setTimeout(connectWs, 3000); };
  ws.onmessage = (e) => { S.snap = JSON.parse(e.data); renderMonitor(); };
}

// ─── Start ───────────────────────────────────────────────────────────
function logout() { store.clear(); location.href = location.pathname; }
$('logout').onclick = logout;
$('reload').onclick = () => { loadRobots(); refreshJob(); };
$('realoff').onclick = () => { if (window.confirm('Tắt REAL?')) act(() => api('/api/real-enable', { method: 'DELETE' }), { ok: 'Đã tắt REAL.' }); };

function noWorkspace() {
  $('strip').hidden = true; document.querySelector('.work').hidden = true;
}

function loop(fn, next) {
  const tick = async () => { if (!document.hidden) await fn(); setTimeout(tick, next()); };
  tick();
}

async function start() {
  S.agent = await fetch('/api/agent').then((r) => r.json()).catch(() => ({ modes: [], auth_required: true }));
  if (!S.f.mode) S.f.mode = (S.agent.modes || []).includes('sim') ? 'sim' : (S.agent.modes || [])[0] || '';
  renderHeader();
  // Opened by the desktop app (#code=...): sign in as the technician signed in to the app, no second login.
  const code = new URLSearchParams(location.hash.slice(1)).get('code');
  // Inside the desktop app the screen is the whole page: no scroll bar of its own (the wheel still scrolls; the STOP bar stays pinned).
  if (code || store.get('vhrs_app') === '1') document.documentElement.classList.add('in-app');
  if (code) {
    try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { /* keep the hash */ }
    // Always take the app's account: a token left from an earlier agent run would expire without a refresh here.
    try {
      const d = await api('/api/screen-login', { method: 'POST', body: { code } });
      store.set('vhrs_token', d.access_token); store.set('vhrs_role', d.role || ''); store.set('vhrs_name', d.name || '');
      store.set('vhrs_app', '1');
      location.reload();
      return;
    } catch (err) { /* fall back to the login form */ }
  }
  if (!S.bearer && !S.viewerToken) {
    $('login').hidden = false; $('controlbar').hidden = true;
    $('loginform').onsubmit = async (e) => {
      e.preventDefault();
      try {
        const d = await api('/api/login', { method: 'POST', body: { email: $('em').value, password: $('pw').value } });
        store.set('vhrs_token', d.access_token); store.set('vhrs_role', d.role || ''); store.set('vhrs_name', d.name || '');
        location.reload();
      } catch (err) { $('loginerr').textContent = errText(err); }
    };
    return;
  }
  $('who').textContent = S.name ? S.name + (S.role === 'MANAGER' ? ' (Manager)' : '') : '';
  $('logout').hidden = !S.bearer || store.get('vhrs_app') === '1';     // the app signs out for the screen
  $('app').hidden = false;
  connectWs();
  loop(async () => { try { S.agent = await api('/api/agent'); } catch (e) { /* keep the last */ } renderHeader(); renderDetail(); }, () => 2000);
  setInterval(renderHeader, 1000);                                       // the REAL countdown
  if (!S.bearer || (S.role && S.role !== 'TECHNICAL_STAFF')) { noWorkspace(); return; }
  loop(loadRobots, () => (S.robots && (S.robots.active > 0 || S.robots.robots.some((r) => r.level >= 3)) ? 5000 : 15000));
  loop(loadJobs, () => 30000);
  if (S.sel) selectJob(S.sel); else renderDetail(true);
  loop(async () => { if (S.sel && !S.busy) await loadDetail(); }, () => (S.detail && ['WRITING', 'PAUSED'].includes(S.detail.status) ? 5000 : 20000));
}
start();
