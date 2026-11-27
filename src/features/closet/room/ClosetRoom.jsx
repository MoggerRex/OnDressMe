import { useEffect, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import HangingGarment from './HangingGarment';
import FloorShoe from './FloorShoe';
import { CUTS } from './cuts';
import { FLOOR_Z, PER_RAIL, RAILS, RAIL_LEN, RAIL_Y, placeItems, railToWorld, slotAt, slotX, worldToRail } from './layout';

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
      // en detalle de zapatos cámara y zapato se adelantan 20 cm más: el desenfoque queda delante de las prendas
      // colgadas (cuyo dobladillo baja hasta la altura de la cámara) y detrás del zapato al girarlo
      : floor ? railToWorld(rail, scroll.cur, -RAIL_Y + 0.42, FLOOR_Z + 0.62 + (back && back + 0.2))
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

// Arrastrar prendas con el mouse (vista general o de barra). Al presionar, la prenda se levanta; mientras se mantiene
// presionado sigue al puntero a lo largo de la barra (o salta a otra barra); al soltar se acomoda en el lugar más cercano.
const X_MIN = slotX(0), X_MAX = slotX(PER_RAIL - 1);
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), hit = new THREE.Vector3();
const floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

// ¿Sobre qué barra y en qué x está el puntero? Colgadas: plano vertical de cada barra. Zapatos: el piso, junto a la pared.
function pointerOnRail(floor) {
  let best = null;
  RAILS.forEach(({ pos, rotY }, rail) => {
    let local, score;
    if (floor) {
      if (!ray.ray.intersectPlane(floorPlane, hit)) return;
      local = worldToRail(rail, hit);
      if (local.z < -0.5 || local.z > 1.5) return;
      score = Math.abs(local.z - FLOOR_Z);
    } else {
      const normal = new THREE.Vector3(Math.sin(rotY), 0, Math.cos(rotY));
      const plane = new THREE.Plane().setFromNormalAndCoplanarPoint(normal, new THREE.Vector3(...pos));
      if (!ray.ray.intersectPlane(plane, hit)) return;
      if (hit.y < RAIL_Y - 1.8 || hit.y > RAIL_Y + 0.6) return;
      local = worldToRail(rail, hit);
      score = ray.ray.origin.distanceTo(hit);
    }
    if (Math.abs(local.x) > RAIL_LEN / 2 + 0.4) return;
    if (!best || score < best.score) best = { rail, x: THREE.MathUtils.clamp(local.x, X_MIN, X_MAX), score };
  });
  return best;
}

function DragController({ drag, setDrag, held, mode, scroll, onMove }) {
  const { camera, gl } = useThree();
  const pointer = useRef(null);

  useEffect(() => {
    if (!drag) return undefined;
    const toNdc = (e) => {
      const r = gl.domElement.getBoundingClientRect();
      return { x: ((e.clientX - r.left) / r.width) * 2 - 1, y: -((e.clientY - r.top) / r.height) * 2 + 1 };
    };
    const onMoveEv = (e) => {
      pointer.current = toNdc(e);
      if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) > 4) drag.moved = true;
    };
    const onUp = () => {
      if (drag.moved) onMove(drag.id, drag.rail, slotAt(held.x));
      pointer.current = null;
      setDrag(null);
    };
    window.addEventListener('pointermove', onMoveEv);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    document.body.style.cursor = 'grabbing';
    return () => {
      window.removeEventListener('pointermove', onMoveEv);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      document.body.style.cursor = '';
    };
  }, [drag, gl, held, onMove, setDrag]);

  // cada cuadro (la cámara puede estar moviéndose): rayo desde el puntero hasta la barra
  useFrame((_, rawDt) => {
    if (!drag || !drag.moved || !pointer.current) return;
    const dt = Math.min(rawDt, 0.05);
    // cerca del borde de la pantalla la vista de barra se desplaza sola para poder llevarla más lejos
    if (mode === 'rail' && Math.abs(pointer.current.x) > 0.8) {
      scroll.target = THREE.MathUtils.clamp(scroll.target + Math.sign(pointer.current.x) * 1.6 * dt, X_MIN, X_MAX);
    }
    ndc.set(pointer.current.x, pointer.current.y);
    ray.setFromCamera(ndc, camera);
    const on = pointerOnRail(drag.floor);
    if (!on) return;
    held.x = on.x;
    if (on.rail !== drag.rail) setDrag({ ...drag, rail: on.rail });
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

export default function ClosetRoom({ items, nav, scroll, motion, onSelect, onHover, onMove, onGarmentError }) {
  const placed = placeItems(items, isFloor);
  const floor = nav.level === 'floor';
  // drag: { id, rail (barra actual bajo el puntero), floor, sx, sy (inicio en pantalla), moved }; held.x: x del puntero en la barra
  const [drag, setDrag] = useState(null);
  const held = useRef({ x: 0 }).current;
  const grab = (item, pl) => (e) => {
    if (e.button !== 0 || nav.mode === 'detail') return;
    e.stopPropagation();
    held.x = pl.x;
    setDrag({ id: item.id, rail: pl.rail, floor: pl.floor, sx: e.nativeEvent.clientX, sy: e.nativeEvent.clientY, moved: false });
  };
  return (
    <>
      <color attach="background" args={['#14111a']} />
      <ambientLight intensity={0.9} />
      <pointLight position={[0, 2.8, 0]} intensity={14} />
      <pointLight position={[0, 2.6, -2]} intensity={8} />
      <Room />
      <CameraRig mode={nav.mode} rail={nav.rail} floor={floor} scroll={scroll} motion={motion} />
      <DragController drag={drag} setDrag={setDrag} held={held} mode={nav.mode} scroll={scroll} onMove={onMove} />
      {/* zapatos: el seleccionado queda a ~0.6 m de la cámara y los del piso a ~1.1 m */}
      <DetailBackdrop active={nav.mode === 'detail'} dist={floor ? 0.7 : BACKDROP_DIST} />
      {RAILS.map((r, ri) => (
        <mesh key={ri} position={r.pos} rotation={[0, r.rotY, Math.PI / 2]}>
          <cylinderGeometry args={[0.015, 0.015, RAIL_LEN + 0.3, 10]} />
          <meshStandardMaterial color="#c9a45c" metalness={0.8} roughness={0.25} />
        </mesh>
      ))}
      {/* cada prenda en el marco de su barra; al arrastrarla a otra barra solo cambia ese marco (no se vuelve a cargar) */}
      {items.map((item, i) => {
        const pl = placed[i];
        const isHeld = drag?.id === item.id;
        const rail = isHeld ? drag.rail : pl.rail;
        const common = {
          item,
          x: pl.x,
          held: isHeld,
          heldPos: held,
          interactive: nav.mode === 'rail' && rail === nav.rail && pl.floor === floor,
          draggable: nav.mode !== 'detail',
          selected: nav.selected === item.id,
          steps: nav.steps,
          scroll,
          onSelect,
          onHover,
          onGrab: grab(item, pl),
          onError: onGarmentError,
        };
        return (
          <group key={item.id} position={RAILS[rail].pos} rotation={[0, RAILS[rail].rotY, 0]}>
            {pl.floor
              ? <group position={[0, -RAIL_Y, FLOOR_Z]}><FloorShoe {...common} /></group>
              : <HangingGarment {...common} motion={motion} />}
          </group>
        );
      })}
    </>
  );
}
