import * as THREE from 'three';

export const label = 'Tenis / zapatos';
export const floor = true; // va en el piso bajo la barra, no colgado

const LENGTH = 0.3; // m: largo del tenis
const { smoothstep, lerp } = THREE.MathUtils;

// Agujetas: primero por nombre; si el modelo no lo trae, la pieza más alta en promedio de las que no abarcan todo el
// largo del zapato (el cuerpo y la suela sí lo abarcan; las agujetas van arriba, sobre el empeine).
// Se llama ya con el zapato escalado: largo a lo largo de x, suela en y = 0.
function findLaces(meshes, length) {
  const named = meshes.filter((m) => /lace|agujet|cord|string/i.test(`${m.name} ${m.material.name || ''}`));
  if (named.length) return named;
  let best = null, bestY = -Infinity;
  for (const m of meshes) {
    const p = m.geometry.attributes.position;
    m.geometry.computeBoundingBox();
    const bb = m.geometry.boundingBox;
    if (p.count < 50 || bb.max.x - bb.min.x > 0.6 * length) continue;
    let sy = 0;
    for (let i = 0; i < p.count; i++) sy += p.getY(i);
    if (sy / p.count > bestY) { bestY = sy / p.count; best = m; }
  }
  return best ? [best] : [];
}

// Tenis estático (sin física de tela) apoyado en el piso; solo las agujetas se mueven, ancladas donde tocan el zapato.
export function buildShoe(scene) {
  scene.updateMatrixWorld(true);
  const meshes = [];
  scene.traverse((o) => {
    if (!o.isMesh) return;
    const geo = o.geometry.clone();
    geo.applyMatrix4(o.matrixWorld);
    if (!geo.attributes.normal) geo.computeVertexNormals();
    const mat = Array.isArray(o.material) ? o.material.map((m) => m.clone()) : o.material.clone();
    const mesh = new THREE.Mesh(geo, mat);
    mesh.name = o.name;
    meshes.push(mesh);
  });

  // largo del tenis a lo largo de x (de perfil hacia la cámara, como las prendas), suela en y = 0
  const box = new THREE.Box3();
  meshes.forEach((m) => { m.geometry.computeBoundingBox(); box.union(m.geometry.boundingBox); });
  const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const rot = size.z > size.x ? new THREE.Matrix4().makeRotationY(Math.PI / 2) : new THREE.Matrix4();
  const s = LENGTH / (Math.max(size.x, size.z) || 1);
  const mx = new THREE.Matrix4().makeScale(s, s, s).multiply(rot)
    .multiply(new THREE.Matrix4().makeTranslation(-c.x, -box.min.y, -c.z));
  meshes.forEach((m) => m.geometry.applyMatrix4(mx));

  const root = new THREE.Group();
  meshes.forEach((m) => root.add(m));

  // física de agujetas: rígidas donde tocan el zapato (ojales), sueltas en el lazo y las puntas
  const laces = findLaces(meshes, LENGTH);
  const body = meshes.filter((m) => !laces.includes(m));
  const pts = [];
  body.forEach((m) => {
    const p = m.geometry.attributes.position;
    for (let i = 0; i < p.count; i += 3) pts.push(p.getX(i), p.getY(i), p.getZ(i));
  });
  const n = laces.reduce((a, m) => a + m.geometry.attributes.position.count, 0);
  const goal = new Float32Array(n * 3), k = new Float32Array(n), cd = new Float32Array(n), lag = new Float32Array(n);
  const ranges = [];
  let v = 0;
  laces.forEach((m) => {
    m.geometry.attributes.position.setUsage(THREE.DynamicDrawUsage);
    m.frustumCulled = false;
    const p = m.geometry.attributes.position;
    ranges.push({ attr: p, start: v, count: p.count });
    for (let i = 0; i < p.count; i++, v++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      goal[v * 3] = x; goal[v * 3 + 1] = y; goal[v * 3 + 2] = z;
      let d2 = Infinity;
      for (let j = 0; j < pts.length; j += 3) {
        const dx = pts[j] - x, dy = pts[j + 1] - y, dz = pts[j + 2] - z;
        const dd = dx * dx + dy * dy + dz * dz;
        if (dd < d2) d2 = dd;
      }
      const l = smoothstep(Math.sqrt(d2), 0.004, 0.03); // 0 = pegada al zapato, 1 = suelta
      k[v] = lerp(900, 50, l);
      cd[v] = 2 * Math.sqrt(k[v]) * lerp(1.6, 0.45, l);
      lag[v] = 0.035 * l;
    }
  });
  const sim = n ? {
    n, goal, k, c: cd, lag, ranges, ready: false, asleep: false,
    collider: { side: new Float32Array(n) }, // sin choque manga-torso
    pos: new Float32Array(n * 3), vel: new Float32Array(n * 3), last: new Float32Array(16), inv: new THREE.Matrix4(),
  } : null;

  return {
    root,
    sim,
    dispose() {
      meshes.forEach((m) => {
        m.geometry.dispose();
        (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose());
      });
    },
  };
}
