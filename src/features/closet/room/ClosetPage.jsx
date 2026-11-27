import { useEffect, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, PersonStanding, Search, Shirt, SquarePlus, Trash2, Upload, X } from 'lucide-react';
import ClosetRoom, { isFloor } from './ClosetRoom';
import { CUTS } from './cuts';
import { RAILS, SPACING, START_RAIL, freeSlot, placeItems, railRange } from './layout';

// Pistas de teclado (escritorio). En celular se usan los botones táctiles.
const HINTS = {
  overview: '← → cambia de barra · ↑ acercarse · arrastra una prenda para cambiarla de lugar',
  rail: '← → o scroll recorre la barra · clic en una prenda para verla · arrástrala para cambiarla de lugar · ↓ zapatos / alejarse · Esc alejarse',
  floor: '← → o scroll recorre los zapatos · clic en uno para verlo · arrástralo para moverlo · ↑ prendas · ↓ / Esc alejarse',
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
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-slate-950/70 p-4">
      <form
        className="w-full max-w-80 rounded-xl border border-slate-700 bg-slate-900 p-5"
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
  const [panel, setPanel] = useState(false); // pop-up "Mi closet": subir y quitar prendas
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
    setItems((cur) => [...cur, {
      id: crypto.randomUUID(), name, cut, ext: f.name.slice(-3).toLowerCase(), size: f.size, url: URL.createObjectURL(f),
      slot: freeSlot(cur, Boolean(CUTS[cut]?.floor), isFloor),
    }]);
    setPending((cur) => cur.slice(1));
  }

  // Prenda soltada en otro lugar: si ahí había otra de su misma fila (colgada / piso), intercambian lugares.
  function move(id, rail, n) {
    setItems((cur) => {
      const me = cur.find((i) => i.id === id);
      if (!me || (me.slot.rail === rail && me.slot.n === n)) return cur;
      const other = cur.find((i) => i.id !== id && isFloor(i) === isFloor(me) && i.slot.rail === rail && i.slot.n === n);
      return cur.map((i) => (i === me ? { ...i, slot: { rail, n } } : i === other ? { ...i, slot: me.slot } : i));
    });
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

  // Teclas y botones táctiles hacen lo mismo: 'left' | 'right' | 'up' | 'down' | 'back'
  const act = useRef(null);
  act.current = (k) => {
    const { nav: n, range, rangeOf } = live.current;
    // entra a una fila (prendas o zapatos) de la barra actual, empezando en su primer lugar
    const enter = (level) => {
      const r = rangeOf(n.rail, level);
      if (!r) return false;
      scroll.target = scroll.cur = r[0];
      setNav({ ...n, mode: 'rail', level });
      return true;
    };
    const dir = k === 'right' ? 1 : k === 'left' ? -1 : 0;
    if (n.mode === 'overview') {
      if (dir) setNav({ ...n, rail: Math.min(RAILS.length - 1, Math.max(0, n.rail + dir)) });
      else if (k === 'up' && !enter('hang')) enter('floor'); // barra sin prendas: directo a los zapatos
    } else if (n.mode === 'rail') {
      if (dir) scroll.target = clamp(scroll.target + dir * SPACING, range);
      else if (k === 'up') { if (n.level === 'floor') enter('hang'); }
      else if (k === 'down' && n.level === 'hang' && enter('floor')) { /* baja a los zapatos */ }
      else setNav({ ...n, mode: 'overview' }); // ↓ (desde zapatos o sin zapatos) o atrás
    } else if (dir) {
      setNav({ ...n, steps: n.steps + dir });
    } else if (k === 'back') {
      setNav({ ...n, mode: 'rail', selected: null });
    }
  };

  useEffect(() => {
    const KEYS = { ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down', Escape: 'back' };
    function onKey(e) {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return; // escribiendo
      if (!KEYS[e.key]) return;
      e.preventDefault();
      act.current(KEYS[e.key]);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const labelId = nav.mode === 'detail' ? nav.selected : nav.mode === 'rail' ? hoverId : null;
  const shown = items.find((i) => i.id === labelId);
  const shownPl = placed[items.indexOf(shown)];

  // botones táctiles: qué hace cada flecha en el modo actual
  const pad = nav.mode === 'detail'
    ? [['left', ChevronLeft, 'Girar a la izquierda'], ['back', X, 'Regresar a la barra'], ['right', ChevronRight, 'Girar a la derecha']]
    : nav.mode === 'overview'
      ? [['left', ChevronLeft, 'Barra anterior'], ['up', ChevronUp, 'Acercarse'], ['right', ChevronRight, 'Barra siguiente']]
      : [
        ['left', ChevronLeft, 'Anterior'],
        ...(nav.level === 'floor' ? [['up', ChevronUp, 'Prendas']] : []),
        ['down', ChevronDown, nav.level === 'hang' ? 'Zapatos o alejarse' : 'Alejarse'],
        ['right', ChevronRight, 'Siguiente'],
      ];

  return (
    <div className="flex h-[100dvh] flex-col bg-slate-950 text-slate-100">
      <header className="z-10 flex items-center justify-between gap-3 border-b border-slate-800 bg-slate-950/90 px-4 py-3 backdrop-blur sm:px-6">
        <h1 className="shrink-0 bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <div className="flex min-w-0 items-center gap-2">
          <div className="relative min-w-0">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && results[0]) goTo(results[0]);
                if (e.key === 'Escape') { setQuery(''); e.target.blur(); }
              }}
              placeholder="Buscar prenda…"
              aria-label="Buscar prenda"
              className="w-36 rounded-full border border-slate-700 bg-slate-900 py-1.5 pl-9 pr-3 text-sm outline-none focus:border-violet-500 sm:w-56"
            />
            {query.trim() && (
              <ul className="absolute right-0 z-20 mt-2 w-64 max-w-[80vw] overflow-hidden rounded-xl border border-slate-700 bg-slate-900 text-sm shadow-xl">
                {results.map((i) => (
                  <li key={i.id}>
                    <button type="button" onClick={() => goTo(i)} className="block w-full truncate px-4 py-2 text-left hover:bg-slate-800">{i.name}</button>
                  </li>
                ))}
                {!results.length && <li className="px-4 py-2 text-slate-400">Sin resultados</li>}
              </ul>
            )}
          </div>
          <button
            type="button"
            aria-label="Subir prenda"
            onClick={() => setPanel(true)}
            className="shrink-0 rounded-lg p-1.5 text-slate-200 hover:bg-slate-800 hover:text-violet-300"
          >
            <SquarePlus size={24} />
          </button>
        </div>
      </header>

      <main
        className="relative min-h-0 flex-1 touch-none"
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
            onMove={move}
            onGarmentError={remove}
          />
        </Canvas>

        {!items.length && (
          <button
            type="button"
            onClick={() => setPanel(true)}
            className="absolute left-1/2 top-6 flex -translate-x-1/2 items-center gap-2 whitespace-nowrap rounded-full bg-violet-600 px-4 py-2 text-sm font-semibold shadow-lg hover:bg-violet-500"
          >
            <SquarePlus size={16} /> Sube tu primera prenda
          </button>
        )}

        {/* datos: arriba a la izquierda en escritorio; en celular abajo, sobre los botones */}
        {shown && (
          <section className="absolute inset-x-3 bottom-20 rounded-xl border border-slate-800 bg-slate-900/85 p-3 backdrop-blur md:inset-x-auto md:bottom-auto md:left-4 md:top-4 md:w-72 md:p-4">
            <h2 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400 md:mb-3">Datos de la prenda</h2>
            <p className="break-words font-semibold md:text-lg">{shown.name}</p>
            <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-xs md:mt-3 md:gap-y-1.5 md:text-sm">
              <dt className="text-slate-400">Tipo</dt><dd>{CUTS[shown.cut]?.label}</dd>
              <dt className="text-slate-400">Formato</dt><dd>{shown.ext.toUpperCase()} · {(shown.size / 1048576).toFixed(2)} MB</dd>
              <dt className="text-slate-400">Barra</dt><dd>{RAIL_NAMES[shownPl.rail]}{shownPl.floor ? ' (piso)' : ''}</dd>
              <dt className="text-slate-400">Posición</dt><dd>{shownPl.n + 1}</dd>
            </dl>
          </section>
        )}

        <p className="pointer-events-none absolute bottom-4 left-4 hidden rounded-full bg-slate-900/80 px-4 py-2 text-xs text-slate-300 md:block">
          {HINTS[nav.mode === 'rail' && nav.level === 'floor' ? 'floor' : nav.mode]}
        </p>

        {/* controles táctiles (celular / tablet) */}
        <div className="absolute bottom-4 left-1/2 flex -translate-x-1/2 gap-3 md:hidden">
          {pad.map(([k, Icon, label]) => (
            <button
              key={k}
              type="button"
              aria-label={label}
              onClick={() => act.current(k)}
              className="flex size-12 items-center justify-center rounded-full border border-slate-700 bg-slate-900/85 text-slate-100 backdrop-blur active:bg-violet-600"
            >
              <Icon size={22} />
            </button>
          ))}
        </div>
      </main>

      {/* navegación entre secciones, abajo como en una app */}
      <nav className="z-10 flex border-t border-slate-800 bg-slate-950 pb-[env(safe-area-inset-bottom)]">
        <a href="#" className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] text-slate-400 hover:text-slate-100">
          <PersonStanding size={24} /> Probador
        </a>
        <span aria-current="page" className="flex flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-semibold text-pink-300">
          <Shirt size={24} /> Closet
        </span>
      </nav>

      {panel && (
        <div
          className="fixed inset-0 z-20 flex items-center justify-center bg-slate-950/70 p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setPanel(false); }}
          onKeyDown={(e) => { if (e.key === 'Escape') { e.stopPropagation(); setPanel(false); } }}
        >
          <section role="dialog" aria-modal="true" aria-label="Mi closet" className="w-full max-w-sm rounded-xl border border-slate-700 bg-slate-900 p-5 shadow-2xl">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="flex items-center gap-2 font-semibold"><Shirt size={17} /> Mi closet</h2>
              <button type="button" aria-label="Cerrar" onClick={() => setPanel(false)} className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100">
                <X size={18} />
              </button>
            </div>
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
                  setPanel(false);
                }}
              />
            </label>
            <ul className="mt-3 max-h-64 space-y-1 overflow-auto text-sm">
              {items.map((i) => (
                <li key={i.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-800/70 px-3 py-1.5">
                  <span className="truncate">{i.name}</span>
                  <button type="button" aria-label={`Quitar ${i.name}`} onClick={() => remove(i.id)} className="p-1 text-slate-400 hover:text-red-300">
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
              {!items.length && <li className="text-xs text-slate-400">Sube una prenda: la ropa se cuelga en la barra y los zapatos van al piso.</li>}
            </ul>
          </section>
        </div>
      )}

      {pending[0] && (
        <NamePrompt key={pending[0].name + pending.length} file={pending[0]} onSave={savePending} onCancel={() => setPending((cur) => cur.slice(1))} />
      )}
    </div>
  );
}
