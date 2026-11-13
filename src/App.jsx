import { useCallback, useRef, useState } from 'react';
import {
  AlertCircle,
  Download,
  LoaderCircle,
  Sparkles,
  Shirt,
  UserRound,
} from 'lucide-react';
import MannequinScene from './features/mannequin/MannequinScene';
import ClosetDrawer from './features/closet/ClosetDrawer';
import {
  generateAvatar,
  generateGarment,
  getGarmentModel,
  listWardrobe,
} from './services/ondressmeApi';
import useObjectUrl from './hooks/useObjectUrl';

const GARMENT_BLOB_CACHE_LIMIT_BYTES = 32 * 1024 * 1024;

function cacheGarmentBlob(cache, id, blob) {
  cache.delete(id);
  if (blob.size > GARMENT_BLOB_CACHE_LIMIT_BYTES) return;
  cache.set(id, blob);

  let totalBytes = 0;
  for (const cachedBlob of cache.values()) totalBytes += cachedBlob.size;
  while (totalBytes > GARMENT_BLOB_CACHE_LIMIT_BYTES) {
    const oldestEntry = cache.entries().next().value;
    if (!oldestEntry) break;
    cache.delete(oldestEntry[0]);
    totalBytes -= oldestEntry[1].size;
  }
}

function getCachedGarmentBlob(cache, id) {
  const blob = cache.get(id);
  if (!blob) return null;
  cache.delete(id);
  cache.set(id, blob);
  return blob;
}

export default function App() {
  const [bodyPhoto, setBodyPhoto] = useState(null);
  const [garmentType, setGarmentType] = useState('tshirt');
  const [garmentMeshFile, setGarmentMeshFile] = useState(null);
  const [avatarBlob, setAvatarBlob] = useState(null);
  const [avatarId, setAvatarId] = useState(null);
  const [wardrobeItems, setWardrobeItems] = useState([]);
  const [wardrobeLoading, setWardrobeLoading] = useState(false);
  const [garmentModels, setGarmentModels] = useState({});
  const [loadingGarmentId, setLoadingGarmentId] = useState(null);
  const [avatarBusy, setAvatarBusy] = useState(false);
  const [garmentBusy, setGarmentBusy] = useState(false);
  const [error, setError] = useState('');
  const [garmentNotice, setGarmentNotice] = useState('');
  const garmentLoadInProgress = useRef(false);
  const garmentBlobCache = useRef(new Map());

  const avatarUrl = useObjectUrl(avatarBlob);
  const handleGarmentLoaded = useCallback((id) => {
    setLoadingGarmentId((current) => (current === id ? null : current));
  }, []);
  const sceneGarments = Object.entries(garmentModels).map(([id, blob]) => ({
    id,
    blob,
  }));

  async function handleGenerateAvatar() {
    if (!bodyPhoto) return;
    setAvatarBusy(true);
    setError('');
    try {
      const result = await generateAvatar(bodyPhoto);
      setAvatarBlob(result.blob);
      setAvatarId(result.avatarId);
      setWardrobeItems([]);
      setGarmentModels({});
      garmentBlobCache.current.clear();
      setGarmentNotice('');
      if (!result.avatarId) {
        setError(
          'El backend necesita reiniciarse para vincular la ropa con el nuevo maniquí.',
        );
      } else {
        setWardrobeLoading(true);
        try {
          setWardrobeItems(await listWardrobe(result.avatarId));
        } catch (wardrobeError) {
          setError(
            `El maniquí se generó, pero no se pudo cargar su armario: ${wardrobeError.message}`,
          );
        } finally {
          setWardrobeLoading(false);
        }
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setAvatarBusy(false);
    }
  }

  async function handleGenerateGarment() {
    if (!garmentMeshFile || !avatarId) return;
    setGarmentBusy(true);
    setError('');
    setGarmentNotice('');
    try {
      const result = await generateGarment(garmentMeshFile, avatarId, garmentType);
      const pipelineInfo = JSON.parse(result.pipelineInfo || '{}');
      const intersectionPairs = pipelineInfo.metrics?.penetration_triangle_pairs;
      if (!Number.isSafeInteger(intersectionPairs) || intersectionPairs < 0) {
        throw new Error('El backend no devolvió métricas de intersección válidas.');
      }

      const updatedItems = await listWardrobe(avatarId);
      setWardrobeItems(updatedItems);
      const savedGarment = updatedItems.find((item) => item.id === result.garmentId);
      if (!savedGarment) {
        throw new Error('La prenda se procesó, pero no aparece en el armario local.');
      }
      cacheGarmentBlob(garmentBlobCache.current, savedGarment.id, result.blob);
      if (!garmentModels[savedGarment.id]) {
        setLoadingGarmentId(savedGarment.id);
        setGarmentModels((current) => (
          current[savedGarment.id]
            ? current
            : { ...current, [savedGarment.id]: result.blob }
        ));
      }
      setGarmentNotice(
        result.cached
          ? 'Se reutilizó el GLB guardado para este maniquí; no fue necesario repetir la simulación.'
          : intersectionPairs > 0
            ? `La comprobación de superficies detectó ${intersectionPairs} pares de triángulos intersectados; revisa el ajuste.`
            : 'La simulación de Blender terminó; la comprobación superficial no detectó cruces de triángulos.',
      );
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setGarmentBusy(false);
    }
  }

  async function handleWearGarment(item) {
    if (
      !avatarId
      || avatarBusy
      || garmentBusy
      || garmentModels[item.id]
      || garmentLoadInProgress.current
    ) return;
    garmentLoadInProgress.current = true;
    setLoadingGarmentId(item.id);
    setError('');
    let sceneLoadStarted = false;
    try {
      let blob = getCachedGarmentBlob(garmentBlobCache.current, item.id);
      if (!blob) {
        blob = await getGarmentModel(avatarId, item.id);
        cacheGarmentBlob(garmentBlobCache.current, item.id, blob);
      }
      setGarmentModels((current) => (
        current[item.id] ? current : { ...current, [item.id]: blob }
      ));
      sceneLoadStarted = true;
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      garmentLoadInProgress.current = false;
      if (!sceneLoadStarted) setLoadingGarmentId(null);
    }
  }

  function handleToggleWear(item) {
    if (!garmentModels[item.id]) {
      handleWearGarment(item);
      return;
    }

    setGarmentModels((current) => {
      const next = { ...current };
      delete next[item.id];
      return next;
    });
  }

  function handleDropGarment(itemId) {
    const item = wardrobeItems.find((wardrobeItem) => wardrobeItem.id === itemId);
    if (item) handleWearGarment(item);
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6 py-4 backdrop-blur">
        <h1 className="bg-gradient-to-r from-pink-400 to-violet-400 bg-clip-text text-xl font-bold text-transparent">
          OnDressMe
        </h1>
        <span className="text-xs text-slate-400">Prueba virtual 3D</span>
      </header>

      <main className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-6 p-5 lg:grid-cols-[320px_minmax(0,1fr)]">
        <section className="space-y-4">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center gap-3">
              <UserRound className="text-pink-400" size={21} />
              <h2 className="text-lg font-semibold">1. Tu maniquí</h2>
            </div>
            <label className="mb-3 block text-sm text-slate-300" htmlFor="body-photo">
              Selecciona una foto de cuerpo completo
            </label>
            <input
              id="body-photo"
              type="file"
              accept="image/*"
              disabled={avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              onChange={(event) => {
                setBodyPhoto(event.target.files?.[0] || null);
                setAvatarId(null);
                setAvatarBlob(null);
                setWardrobeItems([]);
                setGarmentModels({});
                garmentBlobCache.current.clear();
                setGarmentNotice('');
                setError('');
              }}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700"
            />
            <button
              type="button"
              onClick={handleGenerateAvatar}
              disabled={!bodyPhoto || avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-pink-600 px-4 py-2.5 text-sm font-semibold transition hover:bg-pink-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {avatarBusy ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Sparkles size={17} />
              )}
              {avatarBusy ? 'Generando maniquí...' : 'Generar con SAM 3D Body'}
            </button>
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5">
            <div className="mb-4 flex items-center gap-3">
              <Shirt className="text-violet-400" size={21} />
              <h2 className="text-lg font-semibold">2. Prenda</h2>
            </div>
            <label className="mb-2 block text-sm text-slate-300" htmlFor="garment-type">
              Tipo de prenda
            </label>
            <select
              id="garment-type"
              value={garmentType}
              disabled={!avatarId || avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              onChange={(event) => {
                setGarmentType(event.target.value);
                setGarmentMeshFile(null);
                setGarmentNotice('');
                setError('');
              }}
              className="mb-4 min-h-11 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 text-sm text-slate-100 disabled:opacity-50"
            >
              <option value="tshirt">Camiseta de manga corta</option>
              <option value="pants">Pantalón</option>
            </select>
            <label className="mb-3 block text-sm text-slate-300" htmlFor="garment-mesh">
              Malla 3D de {garmentType === 'pants' ? 'un pantalón' : 'una camiseta'} (GLB u OBJ)
            </label>
            <input
              id="garment-mesh"
              type="file"
              accept=".glb,.obj,model/gltf-binary,model/obj"
              disabled={!avatarId || avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              onChange={(event) => {
                setGarmentMeshFile(event.target.files?.[0] || null);
                setGarmentNotice('');
                setError('');
              }}
              className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-slate-200 hover:file:bg-slate-700 disabled:opacity-50"
            />
            {!avatarId && (
              <p className="mt-2 text-xs text-slate-400">
                Primero genera el maniquí con el backend actualizado.
              </p>
            )}
            <button
              type="button"
              onClick={handleGenerateGarment}
              disabled={!garmentMeshFile || !avatarId || avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              className="mt-3 flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-violet-600 px-4 py-2.5 text-sm font-semibold transition hover:bg-violet-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {garmentBusy ? (
                <LoaderCircle className="animate-spin" size={17} />
              ) : (
                <Shirt size={17} />
              )}
              {garmentBusy
                ? 'Ajustando y simulando...'
                : `Simular ${garmentType === 'pants' ? 'pantalón' : 'camiseta'}`}
            </button>
            <p className="mt-3 text-xs leading-5 text-amber-200/80">
              Una foto no basta para esta etapa. Garment3DGen deforma una malla
              base hacia una malla objetivo (que suele obtenerse con InstantMesh);
              OnDressMe aún no ejecuta esos modelos. Sube aquí la geometría
              resultante. GLB conserva materiales; OBJ se admite para geometría.
            </p>
          </div>

          {avatarId && (
            <ClosetDrawer
              avatarId={avatarId}
              items={wardrobeItems}
              wornIds={Object.keys(garmentModels)}
              loading={wardrobeLoading}
              busy={avatarBusy || garmentBusy || Boolean(loadingGarmentId)}
              onToggleWear={handleToggleWear}
            />
          )}

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
              <h2 className="font-semibold">Vista 3D</h2>
              <p className="text-xs text-slate-400">
                Arrastra para rotar y usa la rueda para acercar. La prenda se
                muestra sobre el cuerpo generado.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {avatarUrl && (
                <a
                  href={avatarUrl}
                  download="avatar_output.glb"
                  className="flex items-center gap-2 rounded-lg bg-slate-800 px-3 py-2 text-xs hover:bg-slate-700"
                >
                  <Download size={15} />
                  Maniquí GLB
                </a>
              )}
            </div>
          </div>
          {garmentBusy && (
            <p role="status" aria-live="polite" className="text-sm text-violet-200">
              Preparando la malla y ejecutando la simulación local en Blender…
              <span className="mt-1 block text-xs text-slate-400">
                Sin límite automático de tiempo. Puede tardar bastante con mallas
                densas; mantén abiertos el backend y esta página.
              </span>
            </p>
          )}
          {loadingGarmentId && (
            <p role="status" aria-live="polite" className="text-sm text-violet-200">
              Cargando la prenda guardada al visor...
            </p>
          )}
          {garmentNotice && (
            <p role="status" className="text-sm text-amber-200">
              {garmentNotice}
            </p>
          )}
          <MannequinScene
            avatarUrl={avatarUrl}
            garments={sceneGarments}
            onDropGarment={handleDropGarment}
            onGarmentLoaded={handleGarmentLoaded}
          />
        </section>
      </main>
    </div>
  );
}
