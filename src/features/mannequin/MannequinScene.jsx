import React, { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows, useGLTF } from '@react-three/drei';

// Componente que maneja el modelo 3D o un fallback avanzado si aún no se sube el .glb
function RealisticMannequin({ isHappy, bodyScale }) {
  const groupRef = useRef();

  // NOTA: Cuando consigas tu modelo .glb, guárdalo en src/assets/ y descomenta la siguiente línea:
  // const { scene } = useGLTF('/src/assets/mannequin.glb');

  // Animación de emotes (Feliz / Triste)
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (groupRef.current) {
      if (isHappy) {
        groupRef.current.position.y = Math.sin(t * 6) * 0.08;
        groupRef.current.rotation.y = Math.sin(t * 3) * 0.15;
      } else {
        groupRef.current.position.y = -0.15;
        groupRef.current.rotation.z = 0.05;
      }
    }
  });

  return (
    <group 
      ref={groupRef} 
      scale={[bodyScale.width, bodyScale.height, bodyScale.width]}
    >
      {/* Si usaras un archivo GLB real, aquí renderizarías <primitive object={scene} /> */}
      
      {/* Maniquí humanoide estilizado provisional con proporciones realistas */}
      <group position={[0, 0, 0]}>
        {/* Cabeza */}
        <mesh position={[0, 1.75, 0]}>
          <sphereGeometry args={[0.18, 32, 32]} />
          <meshStandardMaterial color={isHappy ? "#e0a96d" : "#94a3b8"} roughness={0.3} />
        </mesh>

        {/* Torso / Pecho */}
        <mesh position={[0, 1.2, 0]}>
          <cylinderGeometry args={[0.22, 0.16, 0.7, 32]} />
          <meshStandardMaterial color={isHappy ? "#db2777" : "#475569"} roughness={0.4} />
        </mesh>

        {/* Cintura y Caderas (Simulando proporciones ajustables) */}
        <mesh position={[0, 0.75, 0]}>
          <cylinderGeometry args={[0.16, 0.20, 0.5, 32]} />
          <meshStandardMaterial color={isHappy ? "#ec4899" : "#334155"} roughness={0.4} />
        </mesh>

        {/* Piernas */}
        <mesh position={[-0.11, 0.25, 0]}>
          <capsuleGeometry args={[0.07, 0.7, 16, 16]} />
          <meshStandardMaterial color="#cbd5e1" />
        </mesh>
        <mesh position={[0.11, 0.25, 0]}>
          <capsuleGeometry args={[0.07, 0.7, 16, 16]} />
          <meshStandardMaterial color="#cbd5e1" />
        </mesh>

        {/* Brazos */}
        <mesh position={[-0.32, 1.25, 0]} rotation={[0, 0, -0.1]}>
          <capsuleGeometry args={[0.06, 0.65, 16, 16]} />
          <meshStandardMaterial color="#cbd5e1" />
        </mesh>
        <mesh position={[0.32, 1.25, 0]} rotation={[0, 0, 0.1]}>
          <capsuleGeometry args={[0.06, 0.65, 16, 16]} />
          <meshStandardMaterial color="#cbd5e1" />
        </mesh>
      </group>
    </group>
  );
}

export default function MannequinCanvas({ isHappy, bodyScale }) {
  return (
    <div className="w-full h-[520px] bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl overflow-hidden shadow-2xl relative border border-slate-800">
      <div className="absolute top-4 left-4 z-10 bg-slate-800/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-300">
        Visor 3D Paramétrico - OnDressMe
      </div>
      <Canvas camera={{ position: [0, 1.4, 3.8], fov: 45 }}>
        <ambientLight intensity={0.8} />
        <directionalLight position={[5, 5, 5]} intensity={1.3} />
        <RealisticMannequin isHappy={isHappy} bodyScale={bodyScale} />
        <ContactShadows position={[0, -0.1, 0]} opacity={0.7} scale={10} blur={2.5} far={4} />
        <OrbitControls enableZoom={true} minDistance={2} maxDistance={5.5} maxPolarAngle={Math.PI / 2 + 0.05} />
        <Environment preset="city" />
      </Canvas>
    </div>
  );
}