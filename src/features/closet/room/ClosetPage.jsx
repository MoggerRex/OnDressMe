import { useEffect, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Search, Shirt, Trash2, Upload } from 'lucide-react';
import ClosetRoom, { isFloor } from './ClosetRoom';
import { CUTS } from './cuts';
import { RAILS, SPACING, START_RAIL, placeItems, railRange } from './layout';

const HINTS = {
  overview: '← → cambia de barra · ↑ acercarse',
  rail: '← → o scroll recorre la barra · clic en una prenda para verla · ↓ zapatos / alejarse · Esc alejarse',
  floor: '← → o scroll recorre los zapatos · clic en uno para verlo · ↑ prendas · ↓ / Esc alejarse',
  detail: '← → gira la prenda · Esc la devuelve a la barra',
};

const RAIL_NAMES = ['Izquierda', 'Fondo', 'Derecha'];
const clamp = (v, [a, b]) => Math.min(b, Math.max(a, v));

// Pregunta el nombre con el que se guardará la prenda.
function NamePrompt({ file, onSave, onCancel }) {
  const [name, setName] = useState(file.name.replace(/\.[^.]+$/, ''));
  const [cut, setCut] = useState(
    /tenis|zapat|shoe|sneaker|bota/i.test(file.name) ? 'shoes'
      : /pantal|pant|jean/i.test(file.name) ? 'pants'
        : /larga|long/i.test(file.name) ? 'longSleeve' : 'tshirt',
  );
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70">
      <form
        className="w-80 rounded-xl border border-slate-700 bg-slate-900 p-5"
        onSubmit={(e) => { e.preventDefault(); onSave(name.trim() || file.name, cut); }}
        onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}
      >
        <h3 className="font-semibold">¿Cómo se llama esta prenda?</h3>
        <p className="mt-1 truncate text-xs text-slate-400">{file.name}</p>
        <input
          autoFocus
          value={name}
          onChange={(e) => setName(e.target.value)}
          onFocus={(e) => e.target.select()}
          className="mt-3 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-violet-500"
        />
        <label className="mt-3 block text-xs text-slate-400">
          Tipo de prenda
          <select
            value={cut}
            onChange={(e) => setCut(e.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 outline-none focus:border-violet-500"
          >
            {Object.entries(CUTS).map(([key, c]) => <option key={key} value={key}>{c.label}</option>)}
          </select>
        </label>
        <div className="mt-4 flex justify-end gap-2 text-sm">
          <button type="button" onClick={onCancel} className="rounded-lg px-3 py-2 text-slate-300 hover:bg-slate-800">Cancelar</button>
          <button type="submit" className="rounded-lg bg-violet-600 px-4 py-2 font-semibold hover:bg-violet-500">Guardar</button>
        </div>
      </form>
    </div>
  );
}

// shortcut: prendas solo en memoria, se pierden al recargar; persistir en IndexedDB/backend después.
export default function ClosetPage() {
  const [items, setItems] = useState([]);
  const [pending, setPending] = useState([]); // archivos esperando nombre
  const [query, setQuery] = useState('');
  const [hoverId, setHoverId] = useState(null);
  // level: 'hang' (prendas colgadas) o 'floor' (zapatos en el piso bajo la barra)
  const [nav, setNav] = useState({ mode: 'overview', rail: START_RAIL, level: 'hang', selected: null, steps: 0 });
  const scroll = useRef({ target: 0, cur: 0 }).current; // posición de la cámara a lo largo de la barra (m)
  const motion = useRef({ vel: 0 }).current;
  const live = useRef({});
  const placed = placeItems(items, isFloor);
  const rangeOf = (rail, level) => railRange(placed, rail, level === 'floor');
  live.current = { nav, rangeOf, range: rangeOf(nav.rail, nav.level) || [0, 0] };

  function savePending(name, cut) {
    const f = pending[0];
    setItems((cur) => [...cur, { id: crypto.randomUUID(), name, cut, ext: f.name.slice(-3).toLowerCase(), size: f.size, url: URL.createObjectURL(f) }]);
    setPending((cur) => cur.slice(1));
  }

  function remove(id) {
    setItems((cur) => cur.filter((i) => i.id !== id));
    setNav((n) => (n.selected === id ? { ...n, mode: 'rail', selected: null } : n));
  }

  // Lleva la cámara a la prenda y la abre en vista de detalle.
  function goTo(item) {
    const p = placed[items.indexOf(item)];
    scroll.target = p.x;
    if (p.rail !== live.current.nav.rail) scroll.cur = p.x;
    setNav({ mode: 'detail', rail: p.rail, level: p.floor ? 'floor' : 'hang', selected: item.id, steps: 0 });
    setQuery('');
    document.activeElement?.blur();
  }

  const results = query.trim()
    ? items.filter((i) => i.name.toLowerCase().includes(query.trim().toLowerCase())).slice(0, 6)
    : [];

  useEffect(() => {
    function onKey(e) {
      if (e.target instanceof HTMLInputElement) return; // escribiendo (buscador / nombre)
      const { nav: n, range, rangeOf } = live.current;
      // entra a una fila (prendas o zapatos) de la barra actual, empezando en su primer lugar
      const enter = (level) => {
        const r = rangeOf(n.rail, level);
        if (!r) return false;
        scroll.target = scroll.cur = r[0];
        setNav({ ...n, mode: 'rail', level });
        return true;
      };
      const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!dir && !['ArrowUp', 'ArrowDown', 'Escape'].includes(e.key)) return;
      e.preventDefault();
      if (n.mode === 'overview') {
        if (dir) setNav({ ...n, rail: Math.min(RAILS.length - 1, Math.max(0, n.rail + dir)) });
        else if (e.key === 'ArrowUp' && !enter('hang')) enter('floor'); // barra sin prendas: directo a los zapatos
      } else if (n.mode === 'rail') {
        if (dir) scroll.target = clamp(scroll.target + dir * SPACING, range);
        else if (e.key === 'ArrowUp') { if (n.level === 'floor') enter('hang'); }
        else if (e.key === 'ArrowDown' && n.level === 'hang' && enter('floor')) { /* baja a los zapatos */ }
        else setNav({ ...n, mode: 'overview' }); // ↓ (desde zapatos o sin zapatos) o Esc
      } else if (dir) {
        setNav({ ...n, steps: n.steps + dir });
      } else if (e.key === 'Escape') {
        setNav({ ...n, mode: 'rail', selected: null });
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [scroll]);

  const labelId = nav.mode === 'detail' ? nav.selected : nav.mode === 'rail' ? hoverId : null;
  const shown = items.find((i) => i.id === labelId);
  const shownPl = placed[items.indexOf(shown)];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <h1 className="bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <div className="flex items-center gap-5 text-sm">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && results[0]) goTo(results[0]);
                if (e.key === 'Escape') { setQuery(''); e.target.blur(); }
              }}
              placeholder="Buscar prenda…"
              className="w-56 rounded-full border border-slate-700 bg-slate-900 py-1.5 pl-9 pr-3 outline-none focus:border-violet-500"
            />
            {query.trim() && (
              <ul className="absolute right-0 mt-2 w-64 overflow-hidden rounded-xl border border-slate-700 bg-slate-900 shadow-xl">
                {results.map((i) => (
                  <li key={i.id}>
                    <button type="button" onClick={() => goTo(i)} className="block w-full truncate px-4 py-2 text-left hover:bg-slate-800">{i.name}</button>
                  </li>
                ))}
                {!results.length && <li className="px-4 py-2 text-slate-400">Sin resultados</li>}
              </ul>
            )}
          </div>
          <a href="#" className="text-slate-400 hover:text-slate-100">Probador</a>
          <span className="font-semibold text-pink-300">Closet</span>
        </div>
      </header>

      <main
        className="relative h-[calc(100vh-65px)]"
        onWheel={(e) => {
          if (live.current.nav.mode === 'rail') scroll.target = clamp(scroll.target + (e.deltaX + e.deltaY) * 0.003, live.current.range);
        }}
      >
        <Canvas camera={{ fov: 60, near: 0.05 }}>
          <ClosetRoom
            items={items}
            nav={nav}
            scroll={scroll}
            motion={motion}
            onSelect={(id) => setNav((n) => (n.mode === 'rail' ? { ...n, mode: 'detail', selected: id, steps: 0 } : n))}
            onHover={setHoverId}
            onGarmentError={remove}
          />
        </Canvas>

        <div className="absolute left-4 top-4 w-72 space-y-3">
        <aside className="rounded-xl border border-slate-800 bg-slate-900/85 p-4 backdrop-blur">
          <h2 className="mb-3 flex items-center gap-2 font-semibold"><Shirt size={17} /> Mi closet</h2>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold hover:bg-violet-500">
            <Upload size={16} /> Subir prenda (.glb / .obj)
            <input
              type="file"
              accept=".glb,.obj"
              multiple
              hidden
              onChange={(e) => {
                setPending([...e.target.files].filter((f) => /\.(glb|obj)$/i.test(f.name)));
                e.target.value = '';
              }}
            />
          </label>
          <ul className="mt-3 max-h-48 space-y-1 overflow-auto text-sm">
            {items.map((i) => (
              <li key={i.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-800/70 px-3 py-1.5">
                <span className="truncate">{i.name}</span>
                <button type="button" aria-label={`Quitar ${i.name}`} onClick={() => remove(i.id)} className="text-slate-400 hover:text-red-300">
                  <Trash2 size={14} />
                </button>
              </li>
            ))}
            {!items.length && <li className="text-xs text-slate-400">Sube una prenda: la ropa se cuelga en la barra y los zapatos van al piso.</li>}
          </ul>
        </aside>

        {shown && (
          <section className="rounded-xl border border-slate-800 bg-slate-900/85 p-4 backdrop-blur">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">Datos de la prenda</h2>
            <p className="break-words text-lg font-semibold">{shown.name}</p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt className="text-slate-400">Tipo</dt><dd>{CUTS[shown.cut]?.label}</dd>
              <dt className="text-slate-400">Formato</dt><dd>{shown.ext.toUpperCase()}</dd>
              <dt className="text-slate-400">Tamaño</dt><dd>{(shown.size / 1048576).toFixed(2)} MB</dd>
              <dt className="text-slate-400">Barra</dt><dd>{RAIL_NAMES[shownPl.rail]}{shownPl.floor ? ' (piso)' : ''}</dd>
              <dt className="text-slate-400">Posición</dt><dd>{shownPl.n + 1}</dd>
            </dl>
          </section>
        )}
        </div>

        <p className="pointer-events-none absolute bottom-4 left-4 rounded-full bg-slate-900/80 px-4 py-2 text-xs text-slate-300">
          {HINTS[nav.mode === 'rail' && nav.level === 'floor' ? 'floor' : nav.mode]}
        </p>

        {pending[0] && (
          <NamePrompt key={pending[0].name + pending.length} file={pending[0]} onSave={savePending} onCancel={() => setPending((cur) => cur.slice(1))} />
        )}
      </main>
    </div>
  );
}
