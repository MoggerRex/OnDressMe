import * as THREE from 'three';

export const TARGET_HEIGHT = 0.8; // metros
export const SHIRT_TOP = -0.13; // parte más alta de la prenda, medida desde la barra (origen)
const { smoothstep, lerp, clamp } = THREE.MathUtils;
// Gancho de tamaño fijo, igual para todas las prendas (medido sobre la camisa de manga corta de referencia)
const TIP_X = 0.115, TIP_Y = -0.177, NECK_Y = -0.127;
const FLARE = 0.1; // manga larga: leve apertura hacia afuera al bajar (~6°), como cuelga una manga real

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

  // Torso por franjas de 2 cm: el tramo continuo de tela alrededor del centro (|x| sin huecos de 8 cm o más).
  // Así los puños de una manga larga, que pueden llegar tan abajo como el dobladillo, no cuentan como torso.
  const RB = 0.02, nRows = Math.ceil(h / RB) + 2;
  const rowOf = (y) => clamp(Math.floor((SHIRT_TOP - y) / RB), 0, nRows - 1);
  const occ = Array.from({ length: nRows }, () => new Set());
  each((x, y) => occ[rowOf(y)].add(Math.floor(Math.abs(x) / 0.01)));
  const runEnd = occ.map((set) => { let i = 0, gap = 0; while (gap < 8 && i < 400) { gap = set.has(i) ? 0 : gap + 1; i++; } return (i - gap) * 0.01; });
  const inTorso = (x, y) => Math.abs(x) < runEnd[rowOf(y)];
  const rowExt = new Float32Array(nRows);
  let hw = 0, maxX = 0;
  each((x, y) => {
    maxX = Math.max(maxX, Math.abs(x));
    if (!inTorso(x, y)) return;
    const r = rowOf(y);
    rowExt[r] = Math.max(rowExt[r], Math.abs(x));
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

  // Axila en la pose original: bajando desde arriba, tras pasar por la zona ancha (hombros + mangas pegadas),
  // la primera franja que vuelve al ancho del torso. Por debajo, solo es manga lo que está separado del torso.
  let sleeveBottom = Infinity, wide = false;
  for (let r = 0; r < nRows; r++) {
    if (rowExt[r] > hw * 1.15) wide = true;
    else if (wide && rowExt[r] > 0 && rowExt[r] <= hw * 1.1) { sleeveBottom = SHIRT_TOP - r * RB - 0.01; break; }
  }

  // Pose "A" (mangas ya inclinadas hacia abajo, p. ej. manga larga): el brazo sale del torso bajo la axila.
  // El brazo entero gira casi rígido sobre el borde del hombro hasta quedar vertical, pegado al costado:
  // la orilla exterior de la manga baja recta desde el hombro (sin abultarse ni inclinarse hacia adentro).
  let below = 0;
  each((x, y) => { if (!inTorso(x, y) && smoothstep(Math.abs(x), hw * 0.98, hw * 1.3) > 0.25 && y < sleeveBottom - 0.1) below++; });
  const aPose = below > 50;
  const arm = {};
  if (aPose) {
    theta = 0;
    for (const sg of [1, -1]) {
      let cx = 0, cy = 0, n = 0;
      each((x, y) => { if (sg * x > 0.92 * maxX) { cx += sg * x; cy += y; n++; } });
      const C = [cx / n, cy / n];
      // grosor del brazo: medio ancho horizontal de sus franjas (separadas del torso) corregido por la inclinación
      const lo = new Float32Array(nRows).fill(Infinity), hi = new Float32Array(nRows).fill(-Infinity);
      each((x, y) => {
        if (sg * x <= 0 || inTorso(x, y)) return;
        const r = rowOf(y);
        lo[r] = Math.min(lo[r], sg * x); hi[r] = Math.max(hi[r], sg * x);
      });
      let hs = 0, hn = 0;
      for (let r = 0; r < nRows; r++) if (hi[r] > lo[r]) { hs += (hi[r] - lo[r]) / 2; hn++; }
      const a0 = Math.atan2(py - C[1], C[0] - hw);
      const radius = (hn ? hs / hn : 0.05) * Math.sin(a0);
      const S = [hw + 0.35 * radius, py]; // la manga nace en la orilla del hombro: su borde exterior sigue la línea del hombro
      const ax = C[0] - S[0], ay = C[1] - S[1];
      const alpha = Math.atan2(S[1] - C[1], C[0] - S[0]); // ángulo actual bajo la horizontal
      arm[sg] = { S, ax, ay, len2: ax * ax + ay * ay || 1, rotA: Math.max(0, Math.PI / 2 - FLARE - alpha) };
    }
  }

  const total = parts.reduce((a, { geo }) => a + geo.attributes.position.count, 0);
  const goal = new Float32Array(total * 3);
  // peso de manga con signo (-1..1): 0 en torso; sube suave desde la axila para que la unión manga-torso no se estire
  const side = new Float32Array(total);
  let o = 0;
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position, nr = geo.attributes.normal;
    for (let i = 0; i < p.count; i++, o += 3) {
      let x = p.getX(i), y = p.getY(i);
      const w = smoothstep(Math.abs(x), hw * 0.98, hw * 1.3);
      if (w > 0 && (y >= sleeveBottom || !inTorso(x, y))) side[o / 3] = (x < 0 ? -1 : 1) * smoothstep(w, 0, 0.5);
      if (aPose && side[o / 3]) {
        const sg = x < 0 ? -1 : 1, A = arm[sg];
        const t = ((sg * x - A.S[0]) * A.ax + (y - A.S[1]) * A.ay) / A.len2;
        // hombro: el giro entra gradual a lo largo de la parte alta del brazo: la manga sale del hombro con su inclinación
        // y se va curvando hasta quedar vertical, así el hombro cae en curva redondeada hacia afuera (sin hundirse)
        const blendIn = Math.max(Math.abs(side[o / 3]), smoothstep(t, 0.1, 0.3));
        const f = -sg * A.rotA * smoothstep(t, -0.1, 0.45) * blendIn, cs = Math.cos(f), sn = Math.sin(f);
        const dx = x - sg * A.S[0], dy = y - A.S[1];
        x = sg * A.S[0] + dx * cs - dy * sn;
        y = A.S[1] + dx * sn + dy * cs;
        const nx = nr.getX(i), ny = nr.getY(i);
        nr.setXY(i, nx * cs - ny * sn, nx * sn + ny * cs);
        p.setXY(i, x, y);
      }
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

  // Pose "A": el brazo del modelo viene algo curvado; tras girarlo, cada franja de la manga se centra bajo el hombro
  // para que caiga recta hasta el puño (sin que la muñeca se doble hacia adentro)
  if (aPose) {
    for (const sg of [1, -1]) {
      const lo = new Float32Array(nRows).fill(Infinity), hi = new Float32Array(nRows).fill(-Infinity);
      for (let v = 0; v < total; v++) {
        if (side[v] * sg < 0.5 || goal[v * 3 + 1] > arm[sg].S[1] - 0.05) continue;
        const r = rowOf(goal[v * 3 + 1]);
        lo[r] = Math.min(lo[r], sg * goal[v * 3]); hi[r] = Math.max(hi[r], sg * goal[v * 3]);
      }
      const shift = new Float32Array(nRows);
      for (let r = 0; r < nRows; r++) {
        let sum = 0, cnt = 0;
        for (let j = Math.max(0, r - 2); j <= Math.min(nRows - 1, r + 2); j++) {
          if (hi[j] > lo[j]) { sum += arm[sg].S[0] + (arm[sg].S[1] - (SHIRT_TOP - (j + 0.5) * RB)) * Math.tan(FLARE) - (hi[j] + lo[j]) / 2; cnt++; }
        }
        shift[r] = cnt ? sum / cnt : 0;
      }
      for (let v = 0; v < total; v++) {
        if (side[v] * sg <= 0) continue;
        const y = goal[v * 3 + 1];
        goal[v * 3] += sg * shift[rowOf(y)] * Math.abs(side[v]) * smoothstep(arm[sg].S[1] - y, 0.12, 0.35); // el enderezado empieza bajo el hombro: arriba queda la curva redondeada
      }

    }
  }

  // Gancho fijo: se sube/baja la prenda para que sus hombros queden 4.5 cm sobre las puntas del gancho
  // (el gancho va DENTRO de la prenda; solo el cuello asoma por el cuello de la camisa)
  const tipX = TIP_X, tipY = TIP_Y, neckY = NECK_Y;
  let top = -Infinity;
  for (let i = 0; i < total; i++) {
    if (Math.abs(Math.abs(goal[i * 3]) - tipX) < 0.03) top = Math.max(top, goal[i * 3 + 1]);
  }
  const dy = top > -Infinity ? tipY + 0.045 - top : 0;
  if (dy) {
    for (let i = 1; i < total * 3; i += 3) goal[i] += dy;
    parts.forEach(({ geo }) => geo.translate(0, dy, 0));
  }
  const yTop = SHIRT_TOP + dy;
  sleeveBottom += dy;
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
  // Manga apoyada en reposo: la manga entera se desplaza hacia afuera (como un bloque, sin doblarse) lo justo
  // para que ninguna parte entre al torso. Desplazar por franjas doblaba hombros y puños.
  for (const sg of aPose ? [] : [1, -1]) { // en pose "A" la manga ya cuelga en su sitio: solo el choque fino al dibujar
    let need = 0;
    for (let v = 0; v < total; v++) {
      if (side[v] * sg < 0.5) continue;
      const bi = clamp(Math.floor((yTop - goal[v * 3 + 1]) / BIN), 0, nb - 1);
      const z = goal[v * 3 + 2];
      if (bodyW[bi] > 0 && z > zLo[bi] - 0.01 && z < zHi[bi] + 0.01) need = Math.max(need, bodyW[bi] + 0.015 - sg * goal[v * 3]);
    }
    for (let v = 0; v < total; v++) if (side[v] * sg > 0) goal[v * 3] += sg * need * Math.abs(side[v]);
  }
  const collider = { side, bodyW, zLo, zHi, nb, bin: BIN, top: yTop };

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
  const { side, bodyW, zLo, zHi, nb, bin, top } = sim.collider;
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
          const wall = bodyW[b0] + (bodyW[b0 + 1] - bodyW[b0]) * t + 0.015; // 1.5 cm: evita parpadeo entre manga y torso
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
