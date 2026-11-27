import * as THREE from 'three';
import { CUTS } from './cuts';

export const TARGET_HEIGHT = 0.8; // metros: largo de las prendas de torso (cada corte puede fijar el suyo con `height`)
export const SHIRT_TOP = -0.13; // parte más alta de la prenda, medida desde la barra (origen)
const { smoothstep, lerp, clamp } = THREE.MathUtils;
// Gancho de tamaño fijo, igual para todas las prendas (medido sobre la camisa de manga corta de referencia)
const TIP_X = 0.115, TIP_Y = -0.177, NECK_Y = -0.127;

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

// Normales suaves recalculadas sobre la forma colgada final: promedio por posición (aunque los vértices estén
// duplicados por costuras/UVs). Evita rayas de sombreado donde un giro parcial dejó normales que no coinciden con la tela.
function smoothNormals(parts) {
  const key = (x, y, z) => `${Math.round(x * 1e4)},${Math.round(y * 1e4)},${Math.round(z * 1e4)}`;
  const acc = new Map();
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
  const tri = (p, ia, ib, ic) => {
    a.fromBufferAttribute(p, ia); b.fromBufferAttribute(p, ib); c.fromBufferAttribute(p, ic);
    n.subVectors(c, b).cross(a.clone().sub(b)); // normal de la cara, ponderada por su área
    for (const i of [ia, ib, ic]) {
      const k = key(p.getX(i), p.getY(i), p.getZ(i));
      const v = acc.get(k) || acc.set(k, new THREE.Vector3()).get(k);
      v.add(n);
    }
  };
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position, idx = geo.index;
    const count = idx ? idx.count : p.count;
    for (let t = 0; t < count; t += 3) {
      if (idx) tri(p, idx.getX(t), idx.getX(t + 1), idx.getX(t + 2));
      else tri(p, t, t + 1, t + 2);
    }
  });
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position, nr = geo.attributes.normal;
    for (let i = 0; i < p.count; i++) {
      const v = acc.get(key(p.getX(i), p.getY(i), p.getZ(i)));
      if (v && v.lengthSq() > 0) { n.copy(v).normalize(); nr.setXYZ(i, n.x, n.y, n.z); }
    }
    nr.needsUpdate = true;
  });
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
  return g;
}

// Convierte un modelo cargado (GLB/OBJ) en una prenda colgada del gancho con simulación por partículas.
// Pose de reposo "colgada": las mangas caen girando sobre el hombro. Cada vértice es un resorte amortiguado hacia
// esa pose (en coordenadas de mundo), más flojo mientras más lejos del gancho: así el movimiento del gancho
// (balanceo, levantar, girar) hace que la tela se retrase, se balancee y las mangas oscilen.
export function buildGarment(scene, cut = 'tshirt') {
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
  const cutDef = CUTS[cut] || CUTS.tshirt;
  const h = cutDef.height ?? TARGET_HEIGHT; // largo real colgado, en la misma escala para todas las prendas
  const s = h / (size.y || 1);
  const mx = new THREE.Matrix4().makeTranslation(0, SHIRT_TOP, 0)
    .multiply(new THREE.Matrix4().makeScale(s, s, s))
    .multiply(new THREE.Matrix4().makeTranslation(-c.x, -box.max.y, -c.z));
  parts.forEach(({ geo }) => geo.applyMatrix4(mx));

  const each = (fn) => parts.forEach(({ geo }) => {
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++) fn(p.getX(i), p.getY(i), p.getZ(i));
  });

  // Forma colgada según el corte de la prenda (cada corte en su propio archivo dentro de cuts/)
  const shape = cutDef.pose({ parts, each, h, top: SHIRT_TOP });
  const { goal, side, hw, margin } = shape;
  let { sleeveBottom } = shape;
  if (shape.smoothNormals) smoothNormals(parts);
  const total = goal.length / 3;

  // Gancho fijo: se sube/baja la prenda para que sus hombros queden 4.5 cm sobre las puntas del gancho
  // (el gancho va DENTRO de la prenda; solo el cuello asoma por el cuello de la camisa)
  const tipY = TIP_Y, neckY = NECK_Y;
  // ¿dónde queda la prenda con un gancho de puntas en ±tx? (altura dy para los hombros y centro en profundidad hz)
  const placeFor = (tx) => {
    let top = -Infinity;
    for (let i = 0; i < total; i++) if (Math.abs(Math.abs(goal[i * 3]) - tx) < 0.03) top = Math.max(top, goal[i * 3 + 1]);
    const dy = top > -Infinity ? tipY + 0.045 - top : 0;
    let zMin = Infinity, zMax = -Infinity;
    for (let i = 0; i < total; i++) {
      if (Math.abs(Math.abs(goal[i * 3]) - tx) < 0.05 && goal[i * 3 + 1] + dy > tipY) {
        zMin = Math.min(zMin, goal[i * 3 + 2]); zMax = Math.max(zMax, goal[i * 3 + 2]);
      }
    }
    return { dy, hz: zMin < zMax ? (zMin + zMax) / 2 : 0 };
  };
  // El gancho nunca debe atravesar la prenda: cada punto de sus brazos y travesaño tiene que quedar envuelto por tela
  // (tela más afuera a los lados, y tela delante y detrás). Si no, el gancho se angosta hasta que quepa.
  const fits = (tx, { dy, hz }) => {
    const pts = [];
    for (const t of [0.6, 0.8, 1]) for (const sg of [1, -1]) pts.push([sg * tx * t, neckY + (tipY - neckY) * t]);
    for (const t of [0.5, 0.9]) for (const sg of [1, -1]) pts.push([sg * tx * t, tipY]);
    return pts.every(([px, py]) => {
      let outer = 0, zLo = Infinity, zHi = -Infinity;
      for (let i = 0; i < total; i++) {
        const x = goal[i * 3], y = goal[i * 3 + 1] + dy, z = goal[i * 3 + 2] - hz;
        if (Math.abs(y - py) > 0.015) continue;
        if (Math.sign(x) === Math.sign(px)) outer = Math.max(outer, Math.abs(x));
        if (Math.abs(x - px) < 0.025) { zLo = Math.min(zLo, z); zHi = Math.max(zHi, z); }
      }
      return outer > Math.abs(px) + 0.015 && zLo < -0.008 && zHi > 0.008;
    });
  };
  let tipX = TIP_X, fit = placeFor(tipX);
  while (tipX > 0.04 && !fits(tipX, fit)) { tipX *= 0.92; fit = placeFor(tipX); }
  const { dy, hz: hangerZ } = fit;
  if (dy) {
    for (let i = 1; i < total * 3; i += 3) goal[i] += dy;
    parts.forEach(({ geo }) => geo.translate(0, dy, 0));
  }
  const yTop = SHIRT_TOP + dy;
  sleeveBottom += dy;
  // la prenda se centra en profundidad sobre el gancho (centro del grosor de los hombros/pretina, no de la caja del modelo)
  for (let i = 2; i < total * 3; i += 3) goal[i] -= hangerZ; // la prenda se centra sobre el gancho (el gancho queda sobre la barra)
  parts.forEach(({ geo }) => geo.translate(0, 0, -hangerZ));

  // Colisión manga-torso: perfil del torso colgado en franjas de 2 cm (medio ancho y rango en profundidad).
  // Al dibujar, ningún vértice de manga puede quedar dentro de ese volumen: se apoya sobre el costado.
  const BIN = 0.02, nb = Math.ceil(h / BIN) + 4;
  const bodyW = new Float32Array(nb).fill(-1);
  const zLo = new Float32Array(nb).fill(Infinity), zHi = new Float32Array(nb).fill(-Infinity);
  for (let v = 0; v < total; v++) {
    if (side[v]) continue;
    const bi = clamp(Math.floor((yTop - goal[v * 3 + 1]) / BIN), 0, nb - 1);
    bodyW[bi] = Math.max(bodyW[bi], Math.abs(goal[v * 3]));
    zLo[bi] = Math.min(zLo[bi], goal[v * 3 + 2]); zHi[bi] = Math.max(zHi[bi], goal[v * 3 + 2]);
  }
  // contorno suave: sin escalones entre franjas (producían picos en la axila al girar)
  const raw = bodyW.slice();
  for (let bi = 0; bi < nb; bi++) bodyW[bi] = Math.max(raw[Math.max(0, bi - 1)], raw[bi], raw[Math.min(nb - 1, bi + 1)]);
  const collider = { side, bodyW, zLo, zHi, nb, bin: BIN, top: yTop, margin };

  // Rigidez por vértice: pegada al gancho en la línea de hombros, floja hacia abajo y en las puntas de manga
  const k = new Float32Array(total), cd = new Float32Array(total), lag = new Float32Array(total);
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
    // retraso máximo permitido: 0 sobre los brazos del gancho (la tela va pegada a ellos al mover o girar la prenda), hasta 5 cm abajo
    // retraso que crece despacio hacia el dobladillo: un gradiente brusco (hombro fijo / costillas sueltas) estira el torso al girar
    lag[i] = 0.05 * smoothstep(d, 0.06, 0.45);
    // en la axila se unen manga y torso: si cada una se retrasa distinto la malla se estira al girar, así que ahí se mueven juntas
    const ap = 1 - smoothstep(Math.hypot(Math.abs(x) - hw, y - sleeveBottom), 0.05, 0.25);
    lag[i] *= 1 - 0.6 * ap;
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
    sim: { n: total, goal, k, c: cd, lag, collider, pos: new Float32Array(total * 3), vel: new Float32Array(total * 3), ranges, ready: false, asleep: false, last: new Float32Array(16), inv: new THREE.Matrix4() },
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
  const { side, bodyW, zLo, zHi, nb, bin, top, margin } = sim.collider;
  for (const { attr, start, count } of sim.ranges) {
    const a = attr.array;
    for (let j = 0; j < count; j++) {
      const i = (start + j) * 3, x = p[i], y = p[i + 1], z = p[i + 2];
      let lx = e[0] * x + e[4] * y + e[8] * z + e[12];
      const ly = e[1] * x + e[5] * y + e[9] * z + e[13];
      const lz = e[2] * x + e[6] * y + e[10] * z + e[14];
      const sw = side[start + j];
      if (sw) {
        const fb = (top - ly) / bin - 0.5, b0 = Math.floor(fb), t = fb - b0;
        const bi = Math.round(fb);
        if (b0 >= 0 && b0 + 1 < nb && bodyW[b0] > 0 && bodyW[b0 + 1] > 0 && lz > zLo[bi] - 0.01 && lz < zHi[bi] + 0.01) {
          const sg = sw < 0 ? -1 : 1;
          const wall = bodyW[b0] + (bodyW[b0 + 1] - bodyW[b0]) * t + margin; // separación manga-torso (según el corte)
          // la manga se apoya sobre el torso en vez de atravesarlo (proporcional al peso de manga: transición suave)
          if (sg * lx < wall) lx += sg * (wall - sg * lx) * Math.abs(sw);
        }
      }
      a[j * 3] = lx; a[j * 3 + 1] = ly; a[j * 3 + 2] = lz;
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
  const { n, goal, k, c, lag, pos, vel } = sim;
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
      // la tela nunca se aleja de su forma colgada más que lag[v] (cero en los hombros: el gancho no la atraviesa)
      const ex = pos[i] - wx, ey = pos[i + 1] - wy, ez = pos[i + 2] - wz;
      const d2 = ex * ex + ey * ey + ez * ez, r = lag[v];
      if (d2 > r * r) {
        const f = r / Math.sqrt(d2);
        pos[i] = wx + ex * f; pos[i + 1] = wy + ey * f; pos[i + 2] = wz + ez * f;
        if (!r) vel[i] = vel[i + 1] = vel[i + 2] = 0;
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
