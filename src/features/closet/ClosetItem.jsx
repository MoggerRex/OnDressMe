import { Download, Shirt, Sparkles } from 'lucide-react';
import { getGarmentModelUrl } from '../../services/ondressmeApi';

const garmentLabels = {
  tshirt: 'Camiseta',
  pants: 'Pantalón',
};

export default function ClosetItem({ item, avatarId, isWorn, onToggleWear, disabled }) {
  function handleDragStart(event) {
    event.dataTransfer.setData('text/plain', item.id);
    event.dataTransfer.effectAllowed = 'copy';
  }

  return (
    <article
      draggable={!disabled}
      onDragStart={handleDragStart}
      className="rounded-xl border border-slate-700 bg-slate-950/70 p-3 transition-colors hover:border-violet-500/70"
    >
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-lg bg-violet-500/10 p-2 text-violet-300" aria-hidden="true">
          <Shirt size={19} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium text-slate-100">{item.name}</h3>
          <p className="mt-1 text-xs text-slate-400">
            {garmentLabels[item.garment_type] || 'Prenda'}
          </p>
        </div>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          aria-pressed={isWorn}
          disabled={disabled}
          onClick={() => onToggleWear(item)}
          className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg bg-violet-700 px-3 py-2 text-xs font-semibold text-white transition-colors hover:bg-violet-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles size={15} aria-hidden="true" />
          {isWorn ? 'Quitar' : 'Vestir'}
        </button>
        <a
          href={getGarmentModelUrl(avatarId, item.id)}
          download={item.download_filename}
          aria-label={`Descargar ${item.name}`}
          className="flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-slate-700 text-slate-300 transition-colors hover:bg-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-300"
        >
          <Download size={16} aria-hidden="true" />
        </a>
      </div>
    </article>
  );
}