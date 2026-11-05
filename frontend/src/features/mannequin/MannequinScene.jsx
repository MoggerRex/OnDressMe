import { Canvas } from '@react-three/fiber';
import { ContactShadows, Environment, OrbitControls } from '@react-three/drei';

function Mannequin({ shirtColor, pantsColor, accessoryColor, shoesColor, hatColor }) {
  return (
    <group position={[0, 0, 0]}>
      <mesh castShadow position={[0, 2.42, 0]} scale={[0.28, 0.34, 0.25]}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshStandardMaterial color="#d39a76" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0, 2.62, -0.015]} scale={[0.285, 0.19, 0.26]}>
        <sphereGeometry args={[1, 32, 24]} />
        <meshStandardMaterial color="#302621" roughness={0.9} />
      </mesh>
      <mesh castShadow position={[0, 2.05, 0]}>
        <cylinderGeometry args={[0.105, 0.12, 0.22, 24]} />
        <meshStandardMaterial color="#c98d6a" roughness={0.76} />
      </mesh>
      <mesh castShadow position={[0, 1.47, 0]} scale={[1, 1, 0.78]}>
        <capsuleGeometry args={[0.34, 0.56, 8, 20]} />
        <meshStandardMaterial color={shirtColor} roughness={0.82} />
      </mesh>
      <mesh castShadow position={[-0.42, 1.43, 0]} rotation={[0, 0, -0.12]}>
        <capsuleGeometry args={[0.105, 0.66, 8, 16]} />
        <meshStandardMaterial color={shirtColor} roughness={0.82} />
      </mesh>
      <mesh castShadow position={[0.42, 1.43, 0]} rotation={[0, 0, 0.12]}>
        <capsuleGeometry args={[0.105, 0.66, 8, 16]} />
        <meshStandardMaterial color={shirtColor} roughness={0.82} />
      </mesh>
      <mesh castShadow position={[-0.43, 0.99, 0.005]}>
        <sphereGeometry args={[0.105, 20, 16]} />
        <meshStandardMaterial color="#d39a76" roughness={0.76} />
      </mesh>
      <mesh castShadow position={[0.43, 0.99, 0.005]}>
        <sphereGeometry args={[0.105, 20, 16]} />
        <meshStandardMaterial color="#d39a76" roughness={0.76} />
      </mesh>
      <mesh castShadow position={[0, 0.86, 0]}>
        <cylinderGeometry args={[0.29, 0.25, 0.34, 24]} />
        <meshStandardMaterial color={pantsColor} roughness={0.86} />
      </mesh>
      {[-0.15, 0.15].map((x) => (
        <group key={x}>
          <mesh castShadow position={[x, 0.43, 0]}>
            <cylinderGeometry args={[0.145, 0.12, 0.72, 20]} />
            <meshStandardMaterial color={pantsColor} roughness={0.86} />
          </mesh>
          <mesh castShadow position={[x, 0.075, 0.07]}>
            <boxGeometry args={[0.27, 0.14, 0.43]} />
            <meshStandardMaterial color={shoesColor} roughness={0.7} />
          </mesh>
        </group>
      ))}
      <mesh castShadow position={[0, 1.72, 0.285]}>
        <sphereGeometry args={[0.085, 20, 16]} />
        <meshStandardMaterial color={accessoryColor} metalness={0.35} roughness={0.4} />
      </mesh>
      <mesh castShadow position={[0, 2.78, 0]}>
        <cylinderGeometry args={[0.24, 0.25, 0.08, 32]} />
        <meshStandardMaterial color={hatColor} roughness={0.8} />
      </mesh>
      <mesh castShadow position={[0, 2.84, -0.02]}>
        <sphereGeometry args={[0.2, 24, 16]} />
        <meshStandardMaterial color={hatColor} roughness={0.8} />
      </mesh>
    </group>
  );
}

export default function MannequinCanvas({ shirtColor, pantsColor, accessoryColor, shoesColor, hatColor }) {
  return (
    <Canvas
      camera={{ position: [3.8, 3.8, 6.5], fov: 34 }}
      dpr={[1, 1.7]}
      shadows
      gl={{ antialias: true, alpha: true }}
    >
      <ambientLight intensity={1.15} />
      <directionalLight castShadow intensity={2.1} position={[3, 6, 4]} />
      <directionalLight intensity={0.75} position={[-4, 3, -2]} />
      <mesh position={[0, -0.13, 0]} receiveShadow castShadow>
        <cylinderGeometry args={[2.12, 2.12, 0.1, 64]} />
        <meshStandardMaterial color="#505258" roughness={0.82} />
      </mesh>
      <mesh position={[0, -0.04, 0]} receiveShadow>
        <cylinderGeometry args={[2.04, 2.04, 0.08, 64]} />
        <meshStandardMaterial color="#777a80" roughness={0.92} />
      </mesh>
      <Mannequin
        accessoryColor={accessoryColor}
        hatColor={hatColor}
        pantsColor={pantsColor}
        shirtColor={shirtColor}
        shoesColor={shoesColor}
      />
      <ContactShadows position={[0, 0.002, 0]} opacity={0.38} scale={4.5} blur={2.3} far={3.5} />
      <OrbitControls
        enablePan={false}
        minDistance={4.5}
        maxDistance={9}
        maxPolarAngle={Math.PI / 2 + 0.06}
        target={[0, 1.42, 0]}
      />
      <Environment preset="city" />
    </Canvas>
  );
}