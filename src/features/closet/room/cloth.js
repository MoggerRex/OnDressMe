import * as THREE from 'three';

export const TARGET_HEIGHT = 0.8; // metros
export const SHIRT_TOP = -0.13; // parte más alta de la prenda, medida desde la barra (origen)
const { smoothstep, lerp, clamp } = THREE.MathUtils;

function segDist(px, py, ax, ay, bx, by) {
  const dx = bx - ax, dy = by - ay;
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy || 1), 0, 1);
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

function segment(a, b, r, mat) {
  const d = new THREE.Vector3().subVectors(b, a);
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r, r, d.length(), 6), mat);
  m.position.copy(a).addScaledVector(d, 0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), d.normalize());
  return m;
}

// Gancho: gancho curvo sobre la barra + dos brazos hasta los hombros + travesaño (como el dibujo).
function buildHanger(tipX, tipY, neckY) {
  const mat = new THREE.MeshStandardMaterial({ color: '#202026', roughness: 0.4, metalness: 0.4 });
  const g = new THREE.Group();
  const pts = [new THREE.Vector3(0, neckY, 0), new THREE.Vector3(0, neckY / 2, 0)];
  for (let a = -90; a <= 200; a += 15) {
    const r = (a * Math.PI) / 180;
    pts.push(new THREE.Vector3(0.028 * Math.cos(r), 0.028 * Math.sin(r), 0));
  }
  g.add(new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 80, 0.0035, 6), mat));
  const N = new THREE.Vector3(0, neckY, 0);
  const R = new THREE.Vector3(tipX, tipY, 0);
  const L = new THREE.Vector3(-tipX, tipY, 0);
  [[N, R], [N, L], [L, R]].forEach(([a, b]) => g.add(segment(a, b, 0.005, mat)));
  [R, L].forEach((p) => {
    const s = new THREE.Mesh(new THREE.SphereGeometry(0.009, 8, 6), mat);
    s.position.copy(p);
    g.add(s);
  });
  return g;
}

// Convierte un modelo cargado (GLB/OBJ) en una prenda colgada del gancho con simulación por partículas.
// Pose de reposo "colgada": las mangas caen girando sobre el hombro. Cada vértice es un resorte amortiguado hacia
// esa pose (en coordenadas de mundo), más flojo mientras más lejos del gancho: así el movimiento del gancho
// (balanceo, levantar, girar) hace que la tela se retrase, se balancee y las mangas oscilen.
export function buildGarment(scene) {
  scene.updateMatrixWorld(true);
  const parts = [];
  scene.traverse((o) => {
    if (!o.isMesh) return;
    const geo = o.geometry.clone();
    geo.applyMatrix4(o.matrixWorld);
    if (!geo.attributes.normal) geo.computeVertexNormals();
    parts.push({ geo, material: o.material });
  });

  const box = new THREE.Box3();
  parts.forEach(({ geo }) => { geo.computeBoundingBox(); box.union(geo.boundingBox); });
  const size = box.getSize(new THREE.Vector3());
  const c = box.getCenter(new THREE.Vector3());
  const s = TARGET_HEIGHT / (size.y || 1);
  const mx = new THREE.Matrix4().makeTranslation(0, SHIRT_TOP, 0)
    .multiply(new THREE.Matrix4().makeScale(s, s, s))
    .multiply(new THREE.Matrix4().makeTranslation(-c.x, -box.max.y, -c.z));
  parts.forEach(({ geo }) => geo.applyMatrix4(mx));

  const h = TARGET_HEIGHT;
  const each = (fn) => parts.forEach(({ geo }) => {
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) fn(p.getX(i), p.getY(i), p.getZ(i));
  });

  // Medidas: ancho del cuerpo (mitad inferior) y largo de manga
  let hw = 0, maxX = 0;
  each((x, y) => {
    maxX = Math.max(maxX, Math.abs(x));
    if (y < SHIRT_TOP - 0.65 * h) hw = Math.max(hw, Math.abs(x));
  });
  hw = hw || maxX;
  const ratio = (maxX - hw) / h;

  // Caída de mangas: girar sobre el hombro hasta que cuelguen (cortas ~55°, largas ~88° bajo la horizontal)
  const px = hw * 0.9, py = SHIRT_TOP - 0.07 * h;
  let theta = 0;
  if (ratio > 0.04) {
    let sy = 0, n = 0;
    each((x, y) => { if (Math.abs(x) > 0.92 * maxX) { sy += y; n++; } });
    const slope = Math.atan2(py - sy / n, maxX - px);
    const target = lerp(1.15, 1.54, clamp((ratio - 0.2) / 0.35, 0, 1));
    theta = Math.max(0, target - slope);
  }

  const total = parts.reduce((a, { geo }) => a + geo.attributes.position.count, 0);
  const goal = new Float32Array(total * 3);
  let o = 0;
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position, nr = geo.attributes.normal;
    for (let i = 0; i < p.count; i++, o += 3) {
      let x = p.getX(i), y = p.getY(i);
      const w = smoothstep(Math.abs(x), hw * 0.98, hw * 1.3);
      if (theta && w) {
        const sg = x < 0 ? -1 : 1, f = -sg * theta * w, cs = Math.cos(f), sn = Math.sin(f);
        const dx = x - sg * px, dy = y - py;
        x = sg * px + dx * cs - dy * sn;
        y = py + dx * sn + dy * cs;
        const nx = nr.getX(i), ny = nr.getY(i);
        nr.setXY(i, nx * cs - ny * sn, nx * sn + ny * cs);
        p.setXY(i, x, y);
      }
      goal[o] = x; goal[o + 1] = y; goal[o + 2] = p.getZ(i);
    }
    nr.needsUpdate = true;
  });

  // Gancho: puntas en los hombros (70% del ancho), cuello arriba al centro
  const tipX = 0.55 * hw;
  let tipY = SHIRT_TOP - 0.03;
  let top = -Infinity;
  for (let i = 0; i < total; i++) {
    if (Math.abs(Math.abs(goal[i * 3]) - tipX) < 0.03) top = Math.max(top, goal[i * 3 + 1]);
  }
  // El gancho va DENTRO de la prenda: la tela de los hombros cae sobre los brazos y solo el cuello asoma por el cuello de la camisa
  if (top > -Infinity) tipY = top - 0.045;
  const neckY = tipY + 0.05;
  // Centro (en profundidad) del grosor de los hombros: es donde debe quedar el gancho, no el centro de la caja del modelo
  let zMin = Infinity, zMax = -Infinity;
  for (let i = 0; i < total; i++) {
    if (Math.abs(Math.abs(goal[i * 3]) - tipX) < 0.05 && goal[i * 3 + 1] > tipY) {
      zMin = Math.min(zMin, goal[i * 3 + 2]); zMax = Math.max(zMax, goal[i * 3 + 2]);
    }
  }
  const hangerZ = zMin < zMax ? (zMin + zMax) / 2 : 0;
  for (let i = 2; i < total * 3; i += 3) goal[i] -= hangerZ; // la prenda se centra sobre el gancho (el gancho queda sobre la barra)
  parts.forEach(({ geo }) => geo.translate(0, 0, -hangerZ));

  // Rigidez por vértice: pegada al gancho en la línea de hombros, floja hacia abajo y en las puntas de manga
  const k = new Float32Array(total), cd = new Float32Array(total);
  for (let i = 0; i < total; i++) {
    const x = goal[i * 3], y = goal[i * 3 + 1];
    const d = Math.min(
      segDist(x, y, 0, neckY, tipX, tipY),
      segDist(x, y, 0, neckY, -tipX, tipY),
    );
    const l = smoothstep(d, 0.03, 0.55 * h);
    k[i] = lerp(900, 80, Math.pow(l, 0.7));
    // arriba (hombros) casi rígido y sobreamortiguado; abajo y en mangas algo subamortiguado: se mueve natural y se asienta en ~1 s
    cd[i] = 2 * Math.sqrt(k[i]) * lerp(1.6, 0.55, l);
  }

  const root = new THREE.Group();
  const ranges = [];
  let start = 0;
  parts.forEach(({ geo, material }) => {
    geo.attributes.position.setUsage(THREE.DynamicDrawUsage);
    geo.computeBoundingSphere();
    geo.boundingSphere.radius += 0.6; // la tela se mueve: evita descartes por esfera desactualizada
    const mat = Array.isArray(material) ? material.map((m) => m.clone()) : material.clone();
    (Array.isArray(mat) ? mat : [mat]).forEach((m) => { m.side = THREE.DoubleSide; });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.frustumCulled = false;
    root.add(mesh);
    ranges.push({ attr: geo.attributes.position, start, count: geo.attributes.position.count });
    start += geo.attributes.position.count;
  });
  const hanger = buildHanger(tipX, tipY, neckY);
  root.add(hanger);

  return {
    root,
    sim: { n: total, goal, k, c: cd, pos: new Float32Array(total * 3), vel: new Float32Array(total * 3), ranges, ready: false, asleep: false, last: new Float32Array(16), inv: new THREE.Matrix4() },
    dispose() {
      root.traverse((m) => {
        if (!m.isMesh) return;
        m.geometry.dispose();
        (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose());
      });
    },
  };
}

function writeLocal(sim, M) {
  sim.inv.copy(M).invert();
  const e = sim.inv.elements, p = sim.pos;
  for (const { attr, start, count } of sim.ranges) {
    const a = attr.array;
    for (let j = 0; j < count; j++) {
      const i = (start + j) * 3, x = p[i], y = p[i + 1], z = p[i + 2];
      a[j * 3] = e[0] * x + e[4] * y + e[8] * z + e[12];
      a[j * 3 + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
      a[j * 3 + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
    }
    attr.needsUpdate = true;
  }
}

// M = matriz de mundo del grupo que contiene la prenda. Duerme (no cuesta nada) cuando todo está quieto.
export function stepCloth(sim, M, rawDt) {
  const e = M.elements;
  let moved = false;
  for (let j = 0; j < 16; j++) {
    if (Math.abs(e[j] - sim.last[j]) > 1e-5) moved = true;
    sim.last[j] = e[j];
  }
  if (!moved && sim.asleep) return;
  const { n, goal, k, c, pos, vel } = sim;
  if (moved) sim.asleep = false;
  if (!sim.ready) {
    for (let i = 0; i < n * 3; i += 3) {
      const x = goal[i], y = goal[i + 1], z = goal[i + 2];
      pos[i] = e[0] * x + e[4] * y + e[8] * z + e[12];
      pos[i + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
      pos[i + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
    }
    sim.ready = true;
  }
  const h = Math.min(rawDt, 0.033) / 3;
  let energy = 0;
  for (let sub = 0; sub < 3; sub++) {
    energy = 0;
    for (let v = 0; v < n; v++) {
      const i = v * 3, gx = goal[i], gy = goal[i + 1], gz = goal[i + 2];
      const dx = e[0] * gx + e[4] * gy + e[8] * gz + e[12] - pos[i];
      const dy = e[1] * gx + e[5] * gy + e[9] * gz + e[13] - pos[i + 1];
      const dz = e[2] * gx + e[6] * gy + e[10] * gz + e[14] - pos[i + 2];
      const kk = k[v], cc = c[v];
      const wx = pos[i] + dx, wy = pos[i + 1] + dy, wz = pos[i + 2] + dz; // objetivo en mundo
      // la tela no se estira en vertical: el eje Y (mundo) es mucho más rígido y amortiguado que X/Z
      vel[i] += (kk * dx - cc * vel[i]) * h;
      vel[i + 1] += (4 * kk * dy - 2 * cc * vel[i + 1]) * h;
      vel[i + 2] += (kk * dz - cc * vel[i + 2]) * h;
      pos[i] += vel[i] * h; pos[i + 1] += vel[i + 1] * h; pos[i + 2] += vel[i + 2] * h;
      // la tela nunca se aleja mucho de su forma colgada
      const ex = pos[i] - wx, ey = pos[i + 1] - wy, ez = pos[i + 2] - wz;
      const d2 = ex * ex + ey * ey + ez * ez;
      if (d2 > 0.0064) {
        const f = 0.08 / Math.sqrt(d2);
        pos[i] = wx + ex * f; pos[i + 1] = wy + ey * f; pos[i + 2] = wz + ez * f;
      }
      energy += dx * dx + dy * dy + dz * dz + vel[i] * vel[i] + vel[i + 1] * vel[i + 1] + vel[i + 2] * vel[i + 2];
    }
  }
  if (!moved && energy / n < 1e-8) {
    sim.asleep = true;
    for (let i = 0; i < n * 3; i += 3) { // posición exacta de reposo
      const x = goal[i], y = goal[i + 1], z = goal[i + 2];
      pos[i] = e[0] * x + e[4] * y + e[8] * z + e[12];
      pos[i + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
      pos[i + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
    }
    vel.fill(0);
  }
  writeLocal(sim, M);
}
