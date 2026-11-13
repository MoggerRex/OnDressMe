import { useCallback, useEffect } from 'react';
import { Canvas } from '@react-three/fiber';
import {
  ContactShadows,
  Environment,
  OrbitControls,
  useGLTF,
} from '@react-three/drei';
import useObjectUrl from '../../hooks/useObjectUrl';

const pendingDisposals = new WeakMap();

function disposeSceneResources(scene) {
  const geometries = new Set();
  const materials = new Set();
  const textures = new Set();
  const skeletons = new Set();

  scene.traverse((object) => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.material) {
      for (const material of Array.isArray(object.material)
        ? object.material
        : [object.material]) {
        materials.add(material);
      }
    }
    if (object.skeleton) skeletons.add(object.skeleton);
  });

  for (const material of materials) {
    for (const value of Object.values(material)) {
      if (value?.isTexture) textures.add(value);
    }
    for (const uniform of Object.values(material.uniforms || {})) {
      if (uniform.value?.isTexture) textures.add(uniform.value);
    }
  }

  for (const geometry of geometries) geometry.dispose();
  for (const material of materials) material.dispose();
  for (const skeleton of skeletons) skeleton.dispose();
  for (const texture of textures) {
    texture.dispose();
    const image = texture.image;
    if (typeof image?.close === 'function') image.close();
  }
}

function useDisposableGltf(url) {
  const { scene } = useGLTF(url);

  useEffect(() => {
    const pending = pendingDisposals.get(scene);
    if (pending) {
      clearTimeout(pending);
      pendingDisposals.delete(scene);
    }

    return () => {
      // Let StrictMode replay its effect cleanup before releasing shared GLTF resources.
      const timer = setTimeout(() => {
        pendingDisposals.delete(scene);
        useGLTF.clear(url);
        disposeSceneResources(scene);
      }, 0);
      pendingDisposals.set(scene, timer);
    };
  }, [scene, url]);

  return scene;
}

function AvatarModel({ url }) {
  const scene = useDisposableGltf(url);
  return <primitive object={scene} dispose={null} />;
}

function GarmentModel({ id, blob, onLoaded }) {
  const url = useObjectUrl(blob);
  const notifyLoaded = useCallback(() => onLoaded(id), [id, onLoaded]);
  if (!url) return null;

  return <LoadedGltf url={url} onLoaded={notifyLoaded} />;
}

function LoadedGltf({ url, onLoaded }) {
  const scene = useDisposableGltf(url);
  useEffect(() => {
    if (onLoaded) onLoaded();
  }, [onLoaded, scene]);
  return <primitive object={scene} dispose={null} />;
}

export default function MannequinScene({
  avatarUrl,
  garments,
  onDropGarment,
  onGarmentLoaded,
}) {
  function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
  }

  function handleDrop(event) {
    event.preventDefault();
    const garmentId = event.dataTransfer.getData('text/plain');
    if (garmentId) onDropGarment(garmentId);
  }

  return (
    <div
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      className="relative h-[520px] w-full overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950"
    >
      <Canvas camera={{ position: [0, 1.15, 3.2], fov: 42 }}>
        <ambientLight intensity={1.1} />
        <directionalLight position={[3, 5, 4]} intensity={1.8} />
        <directionalLight position={[-3, 2, -4]} intensity={0.7} />
        {avatarUrl && <AvatarModel url={avatarUrl} />}
        {garments.map((garment) => (
          <GarmentModel
            key={garment.id}
            id={garment.id}
            blob={garment.blob}
            onLoaded={onGarmentLoaded}
          />
        ))}
        <ContactShadows
          position={[0, 0, 0]}
          opacity={0.45}
          scale={4}
          blur={2.5}
          far={3}
        />
        <OrbitControls
          target={[0, 0.9, 0]}
          enableDamping
          minDistance={1.2}
          maxDistance={5}
        />
        <Environment preset="city" />
      </Canvas>
      {!avatarUrl && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <p className="rounded-xl border border-slate-700 bg-slate-950/80 px-5 py-3 text-center text-sm text-slate-300">
            Selecciona una foto corporal y genera tu maniquí para comenzar.
          </p>
        </div>
      )}
    </div>
  );
}
