import { useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { Shirt, Trash2, Upload } from 'lucide-react';
import ClosetRoom from './ClosetRoom';

// shortcut: prendas solo en memoria, se pierden al recargar; persistir en IndexedDB/backend después.
export default function ClosetPage() {
  const [items, setItems] = useState([]);
  const controlsRef = useRef();

  function addFiles(files) {
    const glbs = [...files].filter((f) => /\.(glb|obj)$/i.test(f.name));
    setItems((cur) => [
      ...cur,
      ...glbs.map((f) => ({ id: crypto.randomUUID(), name: f.name, ext: f.name.slice(-3).toLowerCase(), url: URL.createObjectURL(f) })),
    ]);
  }

  function remove(id) {
    setItems((cur) => cur.filter((i) => i.id !== id));
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <h1 className="bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <nav className="flex items-center gap-5 text-sm">
          <a href="#" className="text-slate-400 hover:text-slate-100">Probador</a>
          <span className="font-semibold text-pink-300">Closet</span>
        </nav>
      </header>

      <main className="relative h-[calc(100vh-65px)]">
        <div className="h-full cursor-pointer" onClick={() => controlsRef.current?.lock()}>
          <Canvas camera={{ fov: 70, near: 0.05 }}>
            <ClosetRoom items={items} controlsRef={controlsRef} onGarmentError={remove} />
          </Canvas>
        </div>

        <aside className="absolute left-4 top-4 w-72 rounded-xl border border-slate-800 bg-slate-900/85 p-4 backdrop-blur">
          <h2 className="mb-3 flex items-center gap-2 font-semibold"><Shirt size={17} /> Mi closet</h2>
          <label className="flex cursor-pointer items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold hover:bg-violet-500">
            <Upload size={16} /> Subir camisa (.glb / .obj)
            <input
              type="file"
              accept=".glb,.obj"
              multiple
              hidden
              onChange={(e) => { addFiles(e.target.files); e.target.value = ''; }}
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
            {!items.length && <li className="text-xs text-slate-400">Sube una camisa y quedará colgada en la barra.</li>}
          </ul>
          <p className="mt-3 text-xs leading-5 text-slate-400">
            Clic en la escena para entrar · WASD o flechas para caminar · Shift corre · Esc para salir.
          </p>
        </aside>
      </main>
    </div>
  );
}
