import * as THREE from 'three';
import * as tshirt from './tshirt';

const { clamp } = THREE.MathUtils;

export const label = 'Playera manga larga';

// Playera de manga larga: cuelga igual que la de manga corta (mismo giro de mangas sobre el hombro y misma física),
// con la manga más cerrada hacia el cuerpo. Solo cambia cómo se mide la prenda: los modelos de manga larga suelen venir
// en pose "A", con los puños tan abajo como el dobladillo, y medir el torso "a lo bruto" los confundiría con torso.
// ángulo de caída de la manga (rad bajo la horizontal): más cerrado que en manga corta (1.23), porque una manga larga
// colgada cae casi pegada al costado; así también la unión con la axila queda más arriba
const SLEEVE_DROP = 1.42;

export function pose(ctx) {
  const { each, h, top } = ctx;
  // Torso por franjas de 2 cm: el tramo continuo de tela alrededor del centro (|x| sin huecos de 8 cm o más)
  const RB = 0.02, nRows = Math.ceil(h / RB) + 2;
  const rowOf = (y) => clamp(Math.floor((top - y) / RB), 0, nRows - 1);
  const occ = Array.from({ length: nRows }, () => new Set());
  each((x, y) => occ[rowOf(y)].add(Math.floor(Math.abs(x) / 0.01)));
  const runEnd = occ.map((set) => { let i = 0, gap = 0; while (gap < 8 && i < 400) { gap = set.has(i) ? 0 : gap + 1; i++; } return (i - gap) * 0.01; });
  const inTorso = (x, y) => Math.abs(x) < runEnd[rowOf(y)];

  const rowExt = new Float32Array(nRows);
  let hw = 0;
  each((x, y) => {
    if (!inTorso(x, y)) return;
    rowExt[rowOf(y)] = Math.max(rowExt[rowOf(y)], Math.abs(x));
    if (y < top - 0.65 * h) hw = Math.max(hw, Math.abs(x));
  });

  // Axila: bajando desde arriba, tras la zona ancha (hombros + mangas), la primera franja con el ancho del torso
  let sleeveBottom = Infinity, wide = false;
  for (let r = 0; r < nRows; r++) {
    if (rowExt[r] > hw * 1.15) wide = true;
    else if (wide && rowExt[r] > 0 && rowExt[r] <= hw * 1.1) { sleeveBottom = top - r * RB - 0.01; break; }
  }

  return {
    ...tshirt.pose(ctx, {
      hw: hw || undefined,
      sleeveBottom,
      target: SLEEVE_DROP,
      // es manga lo que está sobre la axila o separado del torso (el antebrazo y el puño de la pose "A")
      isSleeve: (x, y) => y >= sleeveBottom || !inTorso(x, y),
    }),
  };
}
