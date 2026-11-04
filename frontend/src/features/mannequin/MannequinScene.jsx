import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows } from '@react-three/drei';

// Un componente de prueba que simula un maniquí geométrico elegante
// (Aquí después puedes cambiarlo por un modelo .glb con useGLTF('/assets/dummy.glb'))
function DummyMannequin({ isHappy }) {
  const groupRef = useRef();

  // Pequeña animación sutil de flotación o reacción basada en el estado
  useFrame((state) => {
    const t = state.clock.getElapsedTime();
    if (isHappy) {
      // Si está feliz, se balancea alegremente o da un pequeño brinco
      groupRef.current.position.y = Math.sin(t * 6) * 0.08;
      groupRef.current.rotation.y = Math.sin(t * 3) * 0.2;
    } else {
      // Si está triste, se encoge un poco
      groupRef.current.position.y = -0.1;
      groupRef.current.rotation.z = 0.1;
    }
  });

  return (
    <group ref={groupRef}>
      {/* Cabeza */}
      <mesh position={[0, 1.8, 0]}>
        <sphereGeometry args={[0.2, 32, 32]} />
        <meshStandardMaterial color={isHappy ? "#e0a96d" : "#94a3b8"} roughness={0.3} />
      </mesh>

      {/* Torso (Simulando ropa o maniquí base) */}
      <mesh position={[0, 1.1, 0]}>
        <cylinderGeometry args={[0.25, 0.18, 1.0, 32]} />
        <meshStandardMaterial color={isHappy ? "#ec4899" : "#64748b"} roughness={0.4} />
      </mesh>

      {/* Extremidades simplificadas para la prueba */}
      <mesh position={[-0.3, 1.2, 0]} rotation={[0, 0, -0.2]}>
        <capsuleGeometry args={[0.07, 0.7, 16, 16]} />
        <meshStandardMaterial color="#cbd5e1" />
      </mesh>
      <mesh position={[0.3, 1.2, 0]} rotation={[0, 0, 0.2]}>
        <capsuleGeometry args={[0.07, 0.7, 16, 16]} />
        <meshStandardMaterial color="#cbd5e1" />
      </mesh>
    </group>
  );
}

export default function MannequinCanvas({ isHappy }) {
  return (
    <div className="w-full h-[500px] bg-gradient-to-b from-slate-900 to-slate-950 rounded-2xl overflow-hidden shadow-2xl relative border border-slate-800">
      <div className="absolute top-4 left-4 z-10 bg-slate-800/80 backdrop-blur px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-300">
        Visor 3D Interactivo - OnDressMe
      </div>
      <Canvas camera={{ position: [0, 1.5, 4], fov: 50 }}>
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 5, 5]} intensity={1.2} />
        <DummyMannequin isHappy={isHappy} />
        <ContactShadows position={[0, 0, 0]} opacity={0.6} scale={10} blur={2.5} far={4} />
        <OrbitControls enableZoom={true} minDistance={2} maxDistance={6} maxPolarAngle={Math.PI / 2 + 0.1} />
        <Environment preset="city" />
      </Canvas>
    </div>
  );
}