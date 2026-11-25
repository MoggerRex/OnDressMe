import { useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import HangingGarment from './HangingGarment';
import { RAILS, RAIL_LEN, placeItems, railToWorld } from './layout';

const W = 8, D = 6, H = 3;

// Cámara estática: en 'overview' mira la barra elegida desde el centro; en 'rail'/'detail' se acerca a ella y sigue a scroll.cur.
function CameraRig({ mode, rail, scroll, motion }) {
  const camera = useThree((s) => s.camera);
  const pos = useRef(null);
  const look = useRef(new THREE.Vector3());

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const prev = scroll.cur;
    scroll.cur = THREE.MathUtils.damp(scroll.cur, scroll.target, 5, dt);
    motion.vel = (scroll.cur - prev) / Math.max(dt, 0.001);

    const near = mode !== 'overview';
    const wantPos = near ? railToWorld(rail, scroll.cur, -0.35, 1.6) : new THREE.Vector3(0, 1.65, 0.6);
    const wantLook = railToWorld(rail, near ? scroll.cur : 0, near ? -0.35 : -0.3, 0);
    if (!pos.current) { pos.current = wantPos.clone(); look.current.copy(wantLook); }
    const k = 1 - Math.exp(-4 * dt);
    pos.current.lerp(wantPos, k);
    look.current.lerp(wantLook, k);
    camera.position.copy(pos.current);
    camera.lookAt(look.current);
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
    </group>
  );
}

export default function ClosetRoom({ items, nav, scroll, motion, onSelect, onHover, onGarmentError }) {
  const placed = placeItems(items);
  return (
    <>
      <color attach="background" args={['#14111a']} />
      <ambientLight intensity={0.9} />
      <pointLight position={[0, 2.8, 0]} intensity={14} />
      <pointLight position={[0, 2.6, -2]} intensity={8} />
      <Room />
      <CameraRig mode={nav.mode} rail={nav.rail} scroll={scroll} motion={motion} />
      {RAILS.map((r, ri) => (
        <group key={ri} position={r.pos} rotation={[0, r.rotY, 0]}>
          <mesh rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.015, 0.015, RAIL_LEN + 0.3, 10]} />
            <meshStandardMaterial color="#c9a45c" metalness={0.8} roughness={0.25} />
          </mesh>
          {items.map((item, i) => placed[i].rail === ri && (
            <HangingGarment
              key={item.id}
              item={item}
              x={placed[i].x}
              interactive={nav.mode === 'rail' && ri === nav.rail}
              selected={nav.selected === item.id}
              steps={nav.steps}
              scroll={scroll}
              motion={motion}
              onSelect={onSelect}
              onHover={onHover}
              onError={onGarmentError}
            />
          ))}
        </group>
      ))}
    </>
  );
}
