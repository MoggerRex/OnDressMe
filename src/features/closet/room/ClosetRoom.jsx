import { useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import HangingGarment from './HangingGarment';
import FloorShoe from './FloorShoe';
import { CUTS } from './cuts';
import { FLOOR_Z, RAILS, RAIL_LEN, RAIL_Y, placeItems, railToWorld } from './layout';

export const isFloor = (item) => Boolean(CUTS[item.cut]?.floor);

const W = 8, D = 6, H = 3;

// Cámara estática: en 'overview' mira la barra elegida desde el centro; en 'rail'/'detail' se acerca a ella y sigue a scroll.cur.
function CameraRig({ mode, rail, floor, scroll, motion }) {
  const camera = useThree((s) => s.camera);
  const pos = useRef(null);
  const look = useRef(new THREE.Vector3());

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const prev = scroll.cur;
    scroll.cur = THREE.MathUtils.damp(scroll.cur, scroll.target, 5, dt);
    motion.vel = (scroll.cur - prev) / Math.max(dt, 0.001);

    const near = mode !== 'overview';
    // en detalle la cámara se aleja 30 cm de la barra (la prenda abierta se adelanta lo mismo): deja espacio para el desenfoque
    const back = mode === 'detail' ? 0.3 : 0;
    // piso (zapatos): la cámara baja y mira la fila de zapatos bajo la barra
    const wantPos = !near ? new THREE.Vector3(0, 1.65, 0.6)
      : floor ? railToWorld(rail, scroll.cur, -RAIL_Y + 0.42, FLOOR_Z + 0.62 + back)
      : railToWorld(rail, scroll.cur, -0.35, 1.6 + back);
    const wantLook = !near ? railToWorld(rail, 0, -0.3, 0)
      : floor ? railToWorld(rail, scroll.cur, -RAIL_Y + 0.12 + (mode === 'detail' ? 0.3 : 0), FLOOR_Z)
      : railToWorld(rail, scroll.cur, -0.35, 0);
    if (!pos.current) { pos.current = wantPos.clone(); look.current.copy(wantLook); }
    const k = 1 - Math.exp(-4 * dt);
    pos.current.lerp(wantPos, k);
    look.current.lerp(wantLook, k);
    camera.position.copy(pos.current);
    camera.lookAt(look.current);
  });
  return null;
}

// Vista detalle: un "vidrio esmerilado" entre la prenda y el resto del cuarto. Su transmisión con rugosidad
// desenfoca lo que hay detrás y lo oscurece un poco, así la prenda sacada resalta sobre el fondo.
const BACKDROP_DIST = 1.4; // m frente a la cámara: detrás de la prenda abierta (~1.15 m) y delante de las colgadas (las mangas de perfil llegan a ~1.55 m)
function DetailBackdrop({ active, dist }) {
  const camera = useThree((s) => s.camera);
  const mesh = useRef();
  const k = useRef(0);
  const dir = useRef(new THREE.Vector3()).current;
  useFrame((_, dt) => {
    k.current = THREE.MathUtils.damp(k.current, active ? 1 : 0, 5, dt);
    const m = mesh.current;
    m.visible = k.current > 0.01;
    if (!m.visible) return;
    camera.getWorldDirection(dir);
    m.position.copy(camera.position).addScaledVector(dir, dist);
    m.quaternion.copy(camera.quaternion);
    const hgt = 2.4 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * dist;
    m.scale.set(hgt * camera.aspect, hgt, 1);
    m.material.roughness = 0.45 * k.current; // desenfoque (se distinguen las formas de atrás, sin detalle)
    m.material.color.setScalar(1 - 0.35 * k.current); // oscurecido suave (no tanto como Pinterest)
  });
  return (
    <mesh ref={mesh} visible={false} renderOrder={-1}>
      <planeGeometry />
      <meshPhysicalMaterial transmission={1} thickness={0} ior={1.5} metalness={0} specularIntensity={0} roughness={0} />
    </mesh>
  );
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
  const placed = placeItems(items, isFloor);
  const floor = nav.level === 'floor';
  return (
    <>
      <color attach="background" args={['#14111a']} />
      <ambientLight intensity={0.9} />
      <pointLight position={[0, 2.8, 0]} intensity={14} />
      <pointLight position={[0, 2.6, -2]} intensity={8} />
      <Room />
      <CameraRig mode={nav.mode} rail={nav.rail} floor={floor} scroll={scroll} motion={motion} />
      {/* zapatos: el seleccionado queda a ~0.6 m de la cámara y los del piso a ~1.1 m */}
      <DetailBackdrop active={nav.mode === 'detail'} dist={floor ? 0.7 : BACKDROP_DIST} />
      {RAILS.map((r, ri) => (
        <group key={ri} position={r.pos} rotation={[0, r.rotY, 0]}>
          <mesh rotation={[0, 0, Math.PI / 2]}>
            <cylinderGeometry args={[0.015, 0.015, RAIL_LEN + 0.3, 10]} />
            <meshStandardMaterial color="#c9a45c" metalness={0.8} roughness={0.25} />
          </mesh>
          {items.map((item, i) => {
            const pl = placed[i];
            if (pl.rail !== ri) return null;
            const common = {
              item,
              x: pl.x,
              interactive: nav.mode === 'rail' && ri === nav.rail && pl.floor === floor,
              selected: nav.selected === item.id,
              steps: nav.steps,
              scroll,
              onSelect,
              onHover,
              onError: onGarmentError,
            };
            return pl.floor
              ? <group key={item.id} position={[0, -RAIL_Y, FLOOR_Z]}><FloorShoe {...common} /></group>
              : <HangingGarment key={item.id} {...common} motion={motion} />;
          })}
        </group>
      ))}
    </>
  );
}
