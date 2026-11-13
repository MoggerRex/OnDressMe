import { LoaderCircle, Shirt } from 'lucide-react';
import ClosetItem from './ClosetItem';

export default function ClosetDrawer({
  avatarId,
  items,
  wornIds,
  loading,
  busy,
  onToggleWear,
}) {
  return (
    <section
      aria-labelledby="closet-title"
      className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5"
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Shirt className="text-violet-400" size={21} aria-hidden="true" />
          <h2 id="closet-title" className="text-lg font-semibold">Tu armario</h2>
        </div>
        <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300">
          {items.length}
        </span>
      </div>
      <p className="mb-4 text-xs leading-5 text-slate-400">
        Arrastra una prenda al maniquí o usa el botón para vestirlo.
      </p>

      {loading ? (
        <p role="status" className="flex items-center gap-2 py-4 text-sm text-slate-300">
          <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
          Cargando prendas guardadas...
        </p>
      ) : items.length === 0 ? (
        <p className="rounded-xl border border-dashed border-slate-700 px-4 py-6 text-center text-sm text-slate-400">
          Aún no hay prendas para este maniquí. Ajusta una malla nueva y se guardará aquí.
        </p>
      ) : (
        <ul className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {items.map((item) => (
            <li key={item.id}>
              <ClosetItem
                item={item}
                avatarId={avatarId}
                isWorn={wornIds.includes(item.id)}
                onToggleWear={onToggleWear}
                disabled={busy}
              />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}