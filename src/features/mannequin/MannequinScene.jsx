import { Canvas } from '@react-three/fiber';
import {
  ContactShadows,
  Environment,
  OrbitControls,
  useGLTF,
} from '@react-three/drei';

function AvatarModel({ url }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

function GarmentModel({ url }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}

export default function MannequinScene({ avatarUrl, garmentUrl }) {
  return (
    <div className="relative h-[520px] w-full overflow-hidden rounded-2xl border border-slate-800 bg-gradient-to-b from-slate-900 to-slate-950">
      <Canvas camera={{ position: [0, 1.15, 3.2], fov: 42 }}>
        <ambientLight intensity={1.1} />
        <directionalLight position={[3, 5, 4]} intensity={1.8} />
        <directionalLight position={[-3, 2, -4]} intensity={0.7} />
        {avatarUrl && <AvatarModel url={avatarUrl} />}
        {garmentUrl && <GarmentModel url={garmentUrl} />}
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
      {!avatarUrl && !garmentUrl && (
        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <p className="rounded-xl border border-slate-700 bg-slate-950/80 px-5 py-3 text-center text-sm text-slate-300">
            Selecciona una foto corporal y genera tu maniquí para comenzar.
          </p>
        </div>
      )}
    </div>
  );
}
