import * as THREE from 'three';

export const label = 'Tenis / zapatos';
export const floor = true; // va en el piso bajo la barra, no colgado

const LENGTH = 0.3; // m: largo del tenis

// Tenis estático (sin física) apoyado en el piso.
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

  return {
    root,
    dispose() {
      meshes.forEach((m) => {
        m.geometry.dispose();
        (Array.isArray(m.material) ? m.material : [m.material]).forEach((x) => x.dispose());
      });
    },
  };
}
