import { useState } from 'react';
import {
  AlertCircle,
  Download,
  LoaderCircle,
  Sparkles,
  UserRound,
} from 'lucide-react';
import MannequinScene from './features/mannequin/MannequinScene';
import { generateAvatar } from './services/ondressmeApi';
import useObjectUrl from './hooks/useObjectUrl';

export default function App() {
  const [bodyPhoto, setBodyPhoto] = useState(null);
  const [avatarBlob, setAvatarBlob] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const avatarUrl = useObjectUrl(avatarBlob);

  async function handleGenerateAvatar() {
    if (!bodyPhoto) return;
    setBusy(true);
    setError('');
    try {
      setAvatarBlob(await generateAvatar(bodyPhoto));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <h1 className="bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <span className="text-xs text-slate-400">Generador de maniquí 3D</span>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 p-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <section>
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center gap-3">
              <UserRound className="text-pink-400" size={21} />
              <h2 className="text-lg font-semibold">Genera tu maniquí</h2>
            </div>
            <label className="mb-3 block text-sm text-slate-300" htmlFor="body-photo">
              Selecciona una foto corporal
            </label>
            <input
              id="body-photo"
              type="file"
              accept="image/*"
              disabled={busy}
              onChange={(event) => {
                setBodyPhoto(event.target.files?.[0] || null);
                setAvatarBlob(null);
                setError('');
              }}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
            />
            <button
              type="button"
              onClick={handleGenerateAvatar}
              disabled={!bodyPhoto || busy}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-pink-600 px-4 py-2.5 text-sm font-semibold transition hover:bg-pink-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}
              {busy ? 'Generando maniquí...' : 'Generar con SAM 3D Body'}
            </button>
          </div>

          {error && (
            <div role="alert" className="mt-5 flex gap-2 rounded-xl border border-red-900 bg-red-950/60 p-4 text-sm text-red-200">
              <AlertCircle className="mt-0.5 shrink-0" size={17} />
              <span>{error}</span>
            </div>
          )}
        </section>

        <section className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div>
              <h2 className="font-semibold">Maniquí 3D</h2>
              <p className="text-xs text-slate-400">
                Arrastra para rotar y usa la rueda para acercar.
              </p>
            </div>
            {avatarUrl && (
              <a
                href={avatarUrl}
                download="avatar_output.glb"
                className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
              >
                <Download size={15} />
                Descargar maniquí
              </a>
            )}
          </div>
          <MannequinScene avatarUrl={avatarUrl} />
        </section>
      </main>
    </div>
  );
}
