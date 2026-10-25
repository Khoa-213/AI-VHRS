// Read-only 3D view of the FAIRINO FR3 V6 and the sheet it writes on: the vendor's URDF + STL meshes posed with the joint angles the
// Robot Agent reports (SIM: from our kinematic model; REAL: from the controller). It shows data; it does not simulate physics and it is
// not a camera. Same drawing code as the agent's own console, fed by the backend instead of a WebSocket.
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import URDFLoader from 'urdf-loader';

THREE.Object3D.DEFAULT_UP.set(0, 0, 1);            // the URDF is Z-up
const MM = 0.001;

export async function startTwin(container, notice, opts) {
  const dark = matchMedia('(prefers-color-scheme: dark)').matches;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(dark ? 0x1b1b1b : 0xf1efe9);
  const camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10);
  camera.position.set(-0.75, -0.75, 0.5);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  container.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(-0.33, 0, 0.12);
  controls.update();

  scene.add(new THREE.HemisphereLight(0xffffff, 0x666666, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-1, -2, 3);
  scene.add(sun);
  const grid = new THREE.GridHelper(2, 20, 0x888888, dark ? 0x333333 : 0xcccccc);
  grid.rotation.x = Math.PI / 2;
  scene.add(grid);
  scene.add(new THREE.AxesHelper(0.15));               // red X, green Y, blue Z at the robot base

  let robot = null;
  const loader = new URDFLoader();
  loader.packages = { fairino_description: opts.packageRoot };
  loader.load(opts.urdfUrl, r => { robot = r; scene.add(r); }, undefined,
              () => { notice.textContent = 'Chưa tải được mô hình robot 3D từ máy chủ.'; notice.hidden = false; });

  // pen: a thin cylinder from the pen tip upward, and a sphere at the tip coloured by force
  const toolLen = (opts.toolMm || 100) * MM;
  const pen = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, toolLen, 12), new THREE.MeshStandardMaterial({ color: 0x2a2a2a }));
  pen.rotation.x = Math.PI / 2;
  const penGroup = new THREE.Group();
  pen.position.z = toolLen / 2;
  penGroup.add(pen);
  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.004, 16, 12), new THREE.MeshStandardMaterial({ color: 0x2e7d32 }));
  penGroup.add(tip);
  penGroup.visible = false;
  scene.add(penGroup);

  // sheet, planned strokes and the written trace, placed with the calibrated paper frame
  let job = null, jobObjs = [], trace = null, traceN = 0, lastTrace = null, lastKey = '';
  const TRACE_MAX = 60000;
  function place(x, y, lift = 0) {
    const f = job.frame, [a, b, c] = f.height_coeffs, h = a * x + b * y + c + lift;
    return new THREE.Vector3(
      (f.origin[0] + x * f.x_axis[0] + y * f.y_axis[0] + h * f.normal[0]) * MM,
      (f.origin[1] + x * f.x_axis[1] + y * f.y_axis[1] + h * f.normal[1]) * MM,
      (f.origin[2] + x * f.x_axis[2] + y * f.y_axis[2] + h * f.normal[2]) * MM);
  }
  function clearJob() { jobObjs.forEach(o => scene.remove(o)); jobObjs = []; trace = null; traceN = 0; lastTrace = null; }
  function buildJob(j) {
    if (!j || !j.frame || !j.pages || !j.pages.length) return false;
    clearJob();
    job = j;
    const pg = j.pages[0];
    const corners = [[0, 0], [pg.width_mm, 0], [pg.width_mm, pg.height_mm], [0, pg.height_mm]].map(([x, y]) => place(x, y, -0.05));
    const geo = new THREE.BufferGeometry().setFromPoints([corners[0], corners[1], corners[2], corners[0], corners[2], corners[3]]);
    geo.computeVertexNormals();
    const sheet = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: 0xffffff, side: THREE.DoubleSide, roughness: 1 }));
    const pos = [];
    pg.strokes.forEach(st => { for (let i = 0; i + 1 < st.length; i++) { const p = place(st[i][0], st[i][1], 0.1), q = place(st[i + 1][0], st[i + 1][1], 0.1); pos.push(p.x, p.y, p.z, q.x, q.y, q.z); } });
    const planned = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)),
                                            new THREE.LineBasicMaterial({ color: dark ? 0x777777 : 0xaaa79d }));
    const tg = new THREE.BufferGeometry();
    tg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(TRACE_MAX * 6), 3));
    tg.setDrawRange(0, 0);
    trace = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({ color: 0x1f4e79 }));
    trace.frustumCulled = false;
    jobObjs = [sheet, planned, trace];
    jobObjs.forEach(o => scene.add(o));
    return true;
  }

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(h, 1);
    camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(container);
  resize();
  (function loop() { requestAnimationFrame(loop); controls.update(); renderer.render(scene, camera); })();

  const tcpColor = new THREE.Color();
  return {
    hasJob: () => job !== null,
    jobId: () => (job ? job.job_id : null),
    setScene(sceneData) { return buildJob(sceneData); },
    update(snap) {
      if (robot && snap.joints_deg) snap.joints_deg.forEach((d, i) => robot.setJointValue('j' + (i + 1), d * Math.PI / 180));
      if (!snap.tcp) return;
      const p = new THREE.Vector3(snap.tcp[0] * MM, snap.tcp[1] * MM, snap.tcp[2] * MM);
      penGroup.position.copy(p);
      penGroup.visible = true;
      const lim = job && job.limits;
      if (lim && snap.force_n !== null && snap.force_n !== undefined) {
        tcpColor.set(snap.force_n > lim.f_hard ? 0xc62828 : snap.force_n > lim.f_max ? 0xef6c00 : snap.force_n >= lim.f_min ? 0x2e7d32 : 0x1565c0);
        tip.material.color.copy(tcpColor);
      }
      const key = snap.job_id + ':' + (snap.state === 'PREFLIGHT' ? 'p' : 'r');
      if (key !== lastKey) { lastKey = key; traceN = 0; lastTrace = null; if (trace) trace.geometry.setDrawRange(0, 0); }
      if (trace && snap.move_kind === 'write' && snap.touching) {
        if (lastTrace && traceN < TRACE_MAX && lastTrace.distanceTo(p) > 0.0004) {
          const a = trace.geometry.attributes.position;
          a.setXYZ(traceN * 2, lastTrace.x, lastTrace.y, lastTrace.z);
          a.setXYZ(traceN * 2 + 1, p.x, p.y, p.z);
          traceN++;
          a.needsUpdate = true;
          trace.geometry.setDrawRange(0, traceN * 2);
        }
        lastTrace = p.clone();
      } else lastTrace = null;
    },
  };
}
