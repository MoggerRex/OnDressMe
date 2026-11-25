import { useEffect, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { PointerLockControls } from '@react-three/drei';
import * as THREE from 'three';
import HangingGarment from './HangingGarment';

const W = 8, D = 6, H = 3, RAIL_Y = 2.0, SPACING = 0.4, PER_RAIL = 17;

// Barras: pared trasera, izquierda y derecha. Las prendas miran hacia el centro.
const RAILS = [
  { start: [-3.2, RAIL_Y, -2.7], step: [SPACING, 0, 0], rotY: 0, len: 6.8, axis: 'x' },
  { start: [-3.7, RAIL_Y, -2.4], step: [0, 0, SPACING], rotY: Math.PI / 2, len: 4.8, axis: 'z' },
  { start: [3.7, RAIL_Y, -2.4], step: [0, 0, SPACING], rotY: -Math.PI / 2, len: 4.8, axis: 'z' },
];

// shortcut: pasadas 51 prendas se reutilizan los mismos huecos (se solapan), ampliar con más barras.
function slotFor(i) {
  const r = RAILS[Math.floor(i / PER_RAIL) % RAILS.length];
  const n = i % PER_RAIL;
  return { position: r.start.map((v, k) => v + r.step[k] * n), rotY: r.rotY };
}

function Player({ player }) {
  const { camera } = useThree();
  const keys = useRef({});

  useEffect(() => {
    camera.position.set(0, 1.6, 2);
    const down = (e) => { keys.current[e.code] = true; };
    const up = (e) => { keys.current[e.code] = false; };
    window.addEventListener('keydown', down);
    window.addEventListener('keyup', up);
    return () => {
      window.removeEventListener('keydown', down);
      window.removeEventListener('keyup', up);
    };
  }, [camera]);

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const k = keys.current;
    const fwd = (k.KeyW || k.ArrowUp ? 1 : 0) - (k.KeyS || k.ArrowDown ? 1 : 0);
    const side = (k.KeyD || k.ArrowRight ? 1 : 0) - (k.KeyA || k.ArrowLeft ? 1 : 0);
    const run = k.ShiftLeft || k.ShiftRight;
    const dir = new THREE.Vector3();
    camera.getWorldDirection(dir);
    dir.y = 0; dir.normalize();
    const right = new THREE.Vector3().crossVectors(dir, camera.up);
    const move = dir.multiplyScalar(fwd).add(right.multiplyScalar(side));
    const moving = move.lengthSq() > 0;
    const speed = run ? 3.2 : 1.8;
    if (moving) move.normalize().multiplyScalar(speed * dt);
    camera.position.x = THREE.MathUtils.clamp(camera.position.x + move.x, -W / 2 + 0.9, W / 2 - 0.9);
    camera.position.z = THREE.MathUtils.clamp(camera.position.z + move.z, -D / 2 + 0.9, D / 2 - 0.6);
    player.pos.copy(camera.position);
    player.speed = moving ? speed / 1.8 : 0;
  });
  return null;
}

function Room() {
  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color="#5b4636" roughness={0.6} />
      </mesh>
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, H, 0]}>
        <planeGeometry args={[W, D]} />
        <meshStandardMaterial color="#e9e4dc" />
      </mesh>
      {[[0, -D / 2, 0, W], [0, D / 2, Math.PI, W], [-W / 2, 0, Math.PI / 2, D], [W / 2, 0, -Math.PI / 2, D]].map(([x, z, ry, w], i) => (
        <mesh key={i} position={[x, H / 2, z]} rotation={[0, ry, 0]}>
          <planeGeometry args={[w, H]} />
          <meshStandardMaterial color="#d9d2c6" roughness={0.9} />
        </mesh>
      ))}
      {RAILS.map((r, i) => (
        <mesh
          key={i}
          position={[r.start[0] + (r.axis === 'x' ? r.len / 2 : 0), RAIL_Y + 0.1, r.start[2] + (r.axis === 'z' ? r.len / 2 : 0)]}
          rotation={r.axis === 'x' ? [0, 0, Math.PI / 2] : [Math.PI / 2, 0, 0]}
        >
          <cylinderGeometry args={[0.015, 0.015, r.len, 10]} />
          <meshStandardMaterial color="#c9a45c" metalness={0.8} roughness={0.25} />
        </mesh>
      ))}
    </group>
  );
}

export default function ClosetRoom({ items, controlsRef, onGarmentError }) {
  const player = useRef({ pos: new THREE.Vector3(), speed: 0 }).current;
  return (
    <>
      <color attach="background" args={['#14111a']} />
      <ambientLight intensity={0.9} />
      <pointLight position={[0, 2.8, 0]} intensity={14} />
      <pointLight position={[0, 2.6, -2]} intensity={8} />
      <Room />
      <Player player={player} />
      <PointerLockControls ref={controlsRef} />
      {items.map((item, i) => (
        <HangingGarment key={item.id} item={item} slot={slotFor(i)} player={player} onError={onGarmentError} />
      ))}
    </>
  );
}
