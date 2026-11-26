import { useEffect, useState } from 'react';
import { LoaderCircle, Scissors } from 'lucide-react';
import { inspectGarment } from '../../services/ondressmeApi';

const NEUTRAL = { width: 1, length: 1 };

function PatternDrawing({ piece, edit }) {
  // Outline segments are in centimetres with y up.
  const points = piece.outline.flatMap(([x1, y1, x2, y2]) => [[x1, y1], [x2, y2]]);
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const reach = 1.45; // room for the largest allowed factor
  const width = (Math.max(...xs) - Math.min(...xs)) * reach || 1;
  const height = (Math.max(...ys) - Math.min(...ys)) * reach || 1;
  const centerX = (Math.max(...xs) + Math.min(...xs)) / 2;
  const centerY = (Math.max(...ys) + Math.min(...ys)) / 2;
  const path = (scaleX, scaleY) => piece.outline
    .map(([x1, y1, x2, y2]) => (
      `M${(x1 - centerX) * scaleX} ${(centerY - y1) * scaleY}L${(x2 - centerX) * scaleX} ${(centerY - y2) * scaleY}`
    ))
    .join('');

  return (
    <svg
      viewBox={`${-width / 2} ${-height / 2} ${width} ${height}`}
      className="h-40 w-full rounded-lg bg-slate-950"
      role="img"
      aria-label={`Patrón de ${piece.name}`}
    >
      <path d={path(1, 1)} stroke="#64748b" strokeWidth="1" fill="none" vectorEffect="non-scaling-stroke" strokeDasharray="3 3" />
      <path d={path(edit.width, edit.length)} stroke={piece.color} strokeWidth="1.5" fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function PatternPanel({
  file,
  avatarId,
  garmentType,
  fit,
  busy,
  onShowPieces,
  onRebuild,
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);
  const [edits, setEdits] = useState({});
  const [exploded, setExploded] = useState(false);

  // Leave the viewer as it was when the file or its settings change.
  useEffect(() => () => onShowPieces(null), [onShowPieces]);

  async function handleInspect() {
    setLoading(true);
    setError('');
    try {
      const result = await inspectGarment(file, avatarId, garmentType, fit);
      setData(result);
      setSelected(result.pieces[0]?.id ?? null);
      setEdits({});
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function toggleExploded(checked) {
    setExploded(checked);
    onShowPieces(checked ? data.piecesBlob : null);
  }

  const piece = data?.pieces.find((item) => item.id === selected);
  const edit = edits[selected] ?? NEUTRAL;
  const changed = Object.fromEntries(
    Object.entries(edits).filter(([, value]) => value.width !== 1 || value.length !== 1),
  );
  const suggestions = data?.body?.suggestions ?? {};

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
      <div className="mb-3 flex items-center gap-3">
        <Scissors className="text-emerald-400" size={21} />
        <h2 className="text-lg font-semibold">3. Piezas y patrones</h2>
      </div>
      <button
        type="button"
        onClick={handleInspect}
        disabled={loading || busy}
        className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-emerald-700 px-4 py-2.5 text-sm font-semibold hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading && <LoaderCircle className="animate-spin" size={17} />}
        {loading ? 'Analizando la malla...' : 'Separar en piezas'}
      </button>
      {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}

      {data && (
        <div className="mt-4 space-y-3 text-sm">
          <p className="text-xs text-slate-400">
            {data.method === 'uv'
              ? 'Cortes tomados del patronaje (UV) que trae la prenda.'
              : 'Cortes calculados por geometría; los bordes siguen los triángulos.'}
          </p>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={exploded} onChange={(event) => toggleExploded(event.target.checked)} />
            Ver las piezas separadas en 3D
          </label>
          <div className="flex flex-wrap gap-2">
            {data.pieces.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelected(item.id)}
                aria-pressed={item.id === selected}
                className={`flex items-center gap-2 rounded-lg border px-2 py-1 text-xs ${item.id === selected ? 'border-slate-200' : 'border-slate-700'}`}
              >
                <span className="h-3 w-3 rounded-full" style={{ background: item.color }} />
                {item.name}
              </button>
            ))}
          </div>

          {piece && (
            <>
              <PatternDrawing piece={piece} edit={edit} />
              <p className="text-xs text-slate-400">
                {(piece.width_cm * edit.width).toFixed(1)} × {(piece.height_cm * edit.length).toFixed(1)} cm
                {' · '}distorsión media del aplanado {(piece.distortion.median * 100).toFixed(1)} %
              </p>
              {[['width', 'Ancho'], ['length', 'Largo']].map(([key, label]) => (
                <label key={key} className="flex items-center gap-2 text-xs">
                  <span className="w-12">{label}</span>
                  <input
                    type="range"
                    min="0.7"
                    max="1.4"
                    step="0.01"
                    value={edit[key]}
                    onChange={(event) => setEdits((current) => ({
                      ...current,
                      [selected]: { ...(current[selected] ?? NEUTRAL), [key]: Number(event.target.value) },
                    }))}
                    className="flex-1"
                  />
                  <span className="w-12 text-right">{Math.round(edit[key] * 100)} %</span>
                </label>
              ))}
            </>
          )}

          {data.body ? (
            <table className="w-full text-xs">
              <thead className="text-slate-400">
                <tr><th className="text-left">Zona</th><th>Cuerpo</th><th>Prenda</th><th>Holgura</th></tr>
              </thead>
              <tbody className="text-center">
                {data.body.measurements.map((row) => (
                  <tr key={row.zone}>
                    <td className="text-left capitalize">{row.zone}</td>
                    <td>{row.body_cm}</td>
                    <td>{row.garment_cm}</td>
                    <td>{row.ease_cm} <span className="text-slate-500">/ {row.wanted_ease_cm}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-xs text-slate-400">Genera el maniquí para comparar medidas.</p>
          )}

          <div className="flex gap-2">
            {Object.keys(suggestions).length > 0 && (
              <button
                type="button"
                onClick={() => setEdits((current) => ({ ...current, ...suggestions }))}
                className="rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
              >
                Usar ajuste sugerido
              </button>
            )}
            <button
              type="button"
              onClick={() => setEdits({})}
              disabled={Object.keys(changed).length === 0}
              className="rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700 disabled:opacity-50"
            >
              Restablecer
            </button>
          </div>
          <button
            type="button"
            onClick={() => {
              setExploded(false);
              onRebuild(Object.keys(changed).length ? changed : null);
            }}
            disabled={!avatarId || busy}
            className="min-h-11 w-full rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Coser las piezas y probar
          </button>
        </div>
      )}
    </div>
  );
}
