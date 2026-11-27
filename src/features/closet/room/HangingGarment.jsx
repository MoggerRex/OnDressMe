import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { useCursor, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { buildGarment, stepCloth, TARGET_HEIGHT } from './cloth';
import { CUTS } from './cuts';

const PROFILE = Math.PI / 2; // colgada de perfil (el frente del modelo mira a +z)
const damp = THREE.MathUtils.damp;

// Un modelo inválido no debe tumbar todo el canvas: simplemente se quita.
class SkipOnError extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

// Jerarquía: place (posición en la barra / sacada) > pivot (balanceo del gancho) > yaw (perfil / giro) > gancho + tela
function HangingModel({ scene, cut, x, interactive, held, heldPos, draggable, onGrab, selected, steps, scroll, motion, onSelect, onHover }) {
  const place = useRef();
  const pivot = useRef();
  const yaw = useRef();
  const swing = useRef({ ax: 0, az: 0, vx: 0.15, vz: 0.1 }); // golpe inicial: se ve viva al colgarla
  const [hovered, setHovered] = useState(false);
  useCursor(hovered && (interactive || draggable) && !held);

  const cloth = useMemo(() => buildGarment(scene, cut), [scene, cut]);
  // en detalle, una prenda más larga (pantalón) sube más para quedar completa y centrada frente a la cámara
  const detailY = 0.22 + ((CUTS[cut]?.height ?? TARGET_HEIGHT) - TARGET_HEIGHT) / 2;
  useEffect(() => () => cloth.dispose(), [cloth]);

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const p = place.current.position;
    const lifted = (hovered && interactive) || held; // presionada (arrastrando) queda levantada como en hover
    const px = p.x;
    // seleccionada: sale de la barra y se coloca frente a la cámara (que está en scroll.cur); arrastrada: sigue al puntero
    p.x = damp(p.x, selected ? scroll.cur : held ? heldPos.x : x, held ? 12 : 7, dt);
    const ty = selected ? detailY : lifted ? 0.15 : 0;
    // sube con la misma suavidad de siempre; al soltarla baja más despacio (antes caía de golpe)
    p.y = damp(p.y, ty, ty < p.y ? 3.5 : 7, dt);
    p.z = damp(p.z, selected ? 0.75 : 0, 7, dt); // a 1.15 m de la cámara (que en detalle está a 1.9 m de la barra)

    const cur = yaw.current.rotation.y;
    // ángulo objetivo (giro del usuario, o perfil en la barra) tomado en su equivalente más cercano: nunca da vueltas de más
    const goal = selected ? steps * PROFILE : PROFILE;
    yaw.current.rotation.y = damp(cur, goal + 2 * Math.PI * Math.round((cur - goal) / (2 * Math.PI)), 8, dt);

    // balanceo del gancho como péndulo sobre la barra (más amortiguado al verla de cerca)
    const s = swing.current;
    const cd = selected ? 9 : 4.5; // un gancho real se asienta en 1-2 balanceos
    s.vz += -motion.vel * 1.5 * dt; // el carrusel arrastra la ropa
    if (held) s.vz += -(p.x - px) * 1.5; // al arrastrarla se mece con su propio movimiento
    s.vx += (-30 * s.ax - cd * s.vx) * dt; s.ax += s.vx * dt;
    s.vz += (-30 * s.az - cd * s.vz) * dt; s.az += s.vz * dt;
    pivot.current.rotation.set(s.ax, 0, s.az);

    yaw.current.updateWorldMatrix(true, false);
    stepCloth(cloth.sim, yaw.current.matrixWorld, dt);
  });

  return (
    <group
      ref={place}
      position={[x, 0, 0]}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true); onHover(true); }}
      onPointerOut={() => { setHovered(false); onHover(false); }}
      onPointerDown={onGrab}
      onClick={(e) => { e.stopPropagation(); if (interactive && e.delta <= 4) onSelect(); }} // delta > 4 px: fue un arrastre
    >
      <group ref={pivot}>
        <group ref={yaw} rotation-y={PROFILE}>
          <primitive object={cloth.root} />
        </group>
      </group>
    </group>
  );
}

const GlbGarment = ({ url, ...rest }) => <HangingModel scene={useGLTF(url).scene} {...rest} />;

// OBJ no trae materiales: se le da uno neutro.
const ObjGarment = ({ url, ...rest }) => {
  const scene = useLoader(OBJLoader, url);
  scene.traverse((o) => { if (o.isMesh) o.material = new THREE.MeshStandardMaterial({ color: '#8fa3c7', roughness: 0.8 }); });
  return <HangingModel scene={scene} {...rest} />;
};

export default function HangingGarment({ item, onError, onSelect, onHover, ...rest }) {
  const Loader = item.ext === 'obj' ? ObjGarment : GlbGarment;
  return (
    <SkipOnError onError={() => onError(item.id)}>
      <Suspense fallback={null}>
        <Loader url={item.url} cut={item.cut} onSelect={() => onSelect(item.id)} onHover={(on) => onHover(on ? item.id : null)} {...rest} />
      </Suspense>
    </SkipOnError>
  );
}
