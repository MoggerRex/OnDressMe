import { useState } from 'react';
import {
  AlertCircle,
  Download,
  LoaderCircle,
  Shirt,
  Sparkles,
  Upload,
  UserRound,
} from 'lucide-react';
import MannequinScene from './features/mannequin/MannequinScene';
import {
  generateAvatar,
  generateGarment,
  simulateGarment,
} from './services/ondressmeApi';
import useObjectUrl from './hooks/useObjectUrl';

function isGlb(file) {
  return file.slice(0, 4).arrayBuffer().then((buffer) => (
    new TextDecoder().decode(buffer) === 'glTF'
  ));
}

export default function App() {
  const [bodyPhoto, setBodyPhoto] = useState(null);
  const [garmentPhoto, setGarmentPhoto] = useState(null);
  const [bodyModel, setBodyModel] = useState(null);
  const [avatarBlob, setAvatarBlob] = useState(null);
  const [garmentBlob, setGarmentBlob] = useState(null);
  const [simulationBlob, setSimulationBlob] = useState(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const avatarUrl = useObjectUrl(avatarBlob);
  const garmentUrl = useObjectUrl(garmentBlob);
  const simulationUrl = useObjectUrl(simulationBlob);

  async function handleBodyModelChange(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    if (!(await isGlb(file))) {
      setError('El modelo seleccionado no es un archivo GLB válido.');
      return;
    }

    setError('');
    setBodyModel({ blob: file, name: file.name });
    setAvatarBlob(file);
    setGarmentBlob(null);
    setSimulationBlob(null);
  }

  async function handleGenerateAvatar() {
    if (!bodyPhoto) return;
    setBusy('body');
    setError('');
    try {
      const blob = await generateAvatar(bodyPhoto);
      setBodyModel({ blob, name: 'avatar_output.glb' });
      setAvatarBlob(blob);
      setGarmentBlob(null);
      setSimulationBlob(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy('');
    }
  }

  async function handleGenerateGarment() {
    if (!garmentPhoto || !bodyModel) return;
    setBusy('garment');
    setError('');
    try {
      const blob = await generateGarment(garmentPhoto, bodyModel.blob);
      setGarmentBlob(blob);
      setSimulationBlob(null);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy('');
    }
  }

  async function handleSimulateGarment() {
    if (!garmentBlob || !bodyModel) return;
    setBusy('simulation');
    setError('');
    try {
      const blob = await simulateGarment(garmentBlob, bodyModel.blob);
      setSimulationBlob(blob);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <h1 className="bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <span className="text-xs text-slate-400">Prototipo local</span>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 p-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <section className="space-y-5">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center gap-3">
              <UserRound className="text-pink-400" size={21} />
              <h2 className="text-lg font-semibold">1. Selecciona tu cuerpo</h2>
            </div>
            <label className="mb-3 block text-sm text-slate-300" htmlFor="body-photo">
              Genera un avatar con una foto corporal
            </label>
            <input
              id="body-photo"
              type="file"
              accept="image/*"
              disabled={Boolean(busy)}
              onChange={(event) => {
                const file = event.target.files?.[0] || null;
                setBodyPhoto(file);
                setBodyModel(null);
                setAvatarBlob(null);
                setGarmentBlob(null);
                setSimulationBlob(null);
                setError('');
              }}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
            />
            <button
              type="button"
              onClick={handleGenerateAvatar}
              disabled={!bodyPhoto || Boolean(busy)}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-pink-600 px-4 py-2.5 text-sm font-semibold transition hover:bg-pink-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === 'body' ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}
              {busy === 'body' ? 'Generando avatar...' : 'Generar avatar con SAM 3D'}
            </button>

            <div className="my-4 flex items-center gap-3 text-xs text-slate-500">
              <span className="h-px flex-1 bg-slate-800" />
              o
              <span className="h-px flex-1 bg-slate-800" />
            </div>
            <label className="mb-2 block text-sm text-slate-300" htmlFor="body-glb">
              Selecciona un avatar existente (.glb)
            </label>
            <input
              id="body-glb"
              type="file"
              accept=".glb,model/gltf-binary"
              disabled={Boolean(busy)}
              onChange={handleBodyModelChange}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
            />
            {bodyModel && (
              <p className="mt-3 break-all text-xs text-emerald-300">
                Cuerpo seleccionado: {bodyModel.name}
              </p>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center gap-3">
              <Shirt className="text-violet-400" size={21} />
              <h2 className="text-lg font-semibold">2. Ajusta una prenda</h2>
            </div>
            <label className="mb-2 block text-sm text-slate-300" htmlFor="garment-photo">
              Foto de camiseta o pantalón
            </label>
            <input
              id="garment-photo"
              type="file"
              accept="image/*"
              disabled={Boolean(busy)}
              onChange={(event) => {
                setGarmentPhoto(event.target.files?.[0] || null);
                setGarmentBlob(null);
                setSimulationBlob(null);
                setError('');
              }}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
            />
            <button
              type="button"
              onClick={handleGenerateGarment}
              disabled={!bodyModel || !garmentPhoto || Boolean(busy)}
              className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === 'garment' ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Upload size={17} />
              )}
              {busy === 'garment' ? 'Ajustando prenda...' : 'Ajustar al cuerpo seleccionado'}
            </button>
            <button
              type="button"
              onClick={handleSimulateGarment}
              disabled={!bodyModel || !garmentBlob || Boolean(busy)}
              className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-700 px-4 py-2.5 text-sm font-semibold transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === 'simulation' ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : null}
              {busy === 'simulation' ? 'Simulando...' : 'Simular tela con Blender'}
            </button>
            {!bodyModel && (
              <p className="mt-3 text-xs text-amber-300">
                Primero genera o selecciona un avatar GLB.
              </p>
            )}
            <p className="mt-4 text-xs leading-5 text-slate-400">
              Se usa una plantilla 3D independiente con la textura de la foto.
              Para simular, configura Blender en{' '}
              <code>BLENDER_EXECUTABLE</code>; sin esa instalación el backend
              responderá con un error explícito.
            </p>
          </div>

          {error && (
            <div role="alert" className="flex gap-2 rounded-xl border border-red-900 bg-red-950/60 p-4 text-sm text-red-200">
              <AlertCircle className="mt-0.5 shrink-0" size={17} />
              <span>{error}</span>
            </div>
          )}
        </section>

        <section className="min-w-0 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/70 px-4 py-3">
            <div>
              <h2 className="font-semibold">Probador 3D</h2>
              <p className="text-xs text-slate-400">
                Arrastra para rotar y usa la rueda para acercar.
              </p>
            </div>
            <div className="flex gap-2">
              {avatarUrl && (
                <a
                  href={avatarUrl}
                  download="avatar_output.glb"
                  className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
                >
                  <Download size={15} />
                  Avatar
                </a>
              )}
              {garmentUrl && (
                <a
                  href={garmentUrl}
                  download="prenda_fit.glb"
                  className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
                >
                  <Download size={15} />
                  Prenda
                </a>
              )}
              {simulationUrl && (
                <a
                  href={simulationUrl}
                  download="prenda_simulada.glb"
                  className="flex items-center gap-2 rounded-lg bg-violet-900 px-3 py-2 text-xs hover:bg-violet-800"
                >
                  <Download size={15} />
                  Simulada
                </a>
              )}
            </div>
          </div>
          <MannequinScene
            avatarUrl={avatarUrl}
            garmentUrl={simulationUrl || garmentUrl}
          />
        </section>
      </main>
    </div>
  );
}
