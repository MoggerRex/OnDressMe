export const label = 'Pantalón';

// Pantalón colgado de la pretina: cuelga tal como viene el modelo (sin mangas que girar). El gancho, la física de
// tela y el balanceo los pone cloth.js igual que en las playeras.
export function pose({ parts, each }) {
  let hw = 0;
  each((x) => { hw = Math.max(hw, Math.abs(x)); });
  const total = parts.reduce((a, { geo }) => a + geo.attributes.position.count, 0);
  const goal = new Float32Array(total * 3);
  let o = 0;
  parts.forEach(({ geo }) => {
    const p = geo.attributes.position;
    for (let i = 0; i < p.count; i++, o += 3) { goal[o] = p.getX(i); goal[o + 1] = p.getY(i); goal[o + 2] = p.getZ(i); }
  });
  // sin mangas: ningún vértice es "manga" y no hay axila
  return { goal, side: new Float32Array(total), hw, sleeveBottom: -Infinity, margin: 0.006 };
}
