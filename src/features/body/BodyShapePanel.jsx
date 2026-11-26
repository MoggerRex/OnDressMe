import { useState } from 'react';

// Same limits as the backend (services/body_shape.py).
const CONTROLS = [
  ['chest', 'Pecho y espalda', 0.85, 1.4],
  ['bust', 'Busto', 0.7, 1.8],
  ['waist', 'Cintura', 0.8, 1.35],
  ['hips', 'Cadera', 0.85, 1.4],
  ['arms', 'Brazos', 0.8, 1.7],
  ['legs', 'Piernas', 0.8, 1.5],
];

const SOURCE_NOTES = {
  foto: 'Medido en tu foto. Corrige lo que la ropa o la pose oculten.',
  manual: 'Ajustado a mano.',
  'sin-segmentacion': 'No hay modelo de silueta; ajusta la complexión a mano.',
  error: 'No se pudo medir la foto; ajusta la complexión a mano.',
};

export default function BodyShapePanel({ shape, busy, onApply }) {
  const [values, setValues] = useState(shape.factors);
  const changed = CONTROLS.some(([key]) => values[key] !== shape.factors[key]);

  return (
    <div className="mt-4 space-y-2 border-t border-slate-800 pt-4">
      <h3 className="text-sm font-semibold">Complexión</h3>
      <p className="text-xs text-slate-400">{SOURCE_NOTES[shape.source]}</p>
      {CONTROLS.map(([key, label, min, max]) => (
        <label key={key} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0">{label}</span>
          <input
            type="range"
            min={min}
            max={max}
            step="0.01"
            value={values[key]}
            onChange={(event) => setValues((current) => ({ ...current, [key]: Number(event.target.value) }))}
            className="min-w-0 flex-1"
          />
          <span className="w-10 text-right">{Math.round(values[key] * 100)} %</span>
        </label>
      ))}
      <button
        type="button"
        onClick={() => onApply(values)}
        disabled={busy || !changed}
        className="min-h-10 w-full rounded-lg bg-slate-800 text-sm font-semibold hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        Aplicar complexión
      </button>
    </div>
  );
}
