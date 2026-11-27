import { Component, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { useCursor, useGLTF } from '@react-three/drei';
import * as THREE from 'three';
import { buildShoe } from './cuts/shoes';

const damp = THREE.MathUtils.damp;
const QUARTER = Math.PI / 2;

class SkipOnError extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

// Jerarquía: place (lugar en el piso / sacado) > yaw (giro en vista detalle) > zapato estático
function ShoeModel({ scene, x, interactive, held, heldPos, draggable, onGrab, selected, steps, scroll, onSelect, onHover }) {
  const place = useRef();
  const yaw = useRef();
  const [hovered, setHovered] = useState(false);
  useCursor(hovered && (interactive || draggable) && !held);

  const shoe = useMemo(() => buildShoe(scene), [scene]);
  useEffect(() => () => shoe.dispose(), [shoe]);

  useFrame((_, rawDt) => {
    const dt = Math.min(rawDt, 0.05);
    const p = place.current.position;
    // hover: se levanta un poco del piso; seleccionado: sube y se acerca a la cámara
    // arrastrado: sigue al puntero y queda levantado como en hover
    p.x = damp(p.x, selected ? scroll.cur : held ? heldPos.x : x, held ? 12 : 7, dt);
    p.y = damp(p.y, selected ? 0.33 : (hovered && interactive) || held ? 0.06 : 0, 7, dt);
    p.z = damp(p.z, selected ? 0.65 : 0, 7, dt); // misma distancia a la cámara (0.47 m) que antes; ClosetRoom adelanta la cámara igual
    const cur = yaw.current.rotation.y, goal = selected ? steps * QUARTER : 0;
    yaw.current.rotation.y = damp(cur, goal + 2 * Math.PI * Math.round((cur - goal) / (2 * Math.PI)), 8, dt);
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
      <group ref={yaw}>
        <primitive object={shoe.root} />
      </group>
    </group>
  );
}

const GlbShoe = ({ url, ...rest }) => <ShoeModel scene={useGLTF(url).scene} {...rest} />;
const ObjShoe = ({ url, ...rest }) => {
  const scene = useLoader(OBJLoader, url);
  scene.traverse((o) => { if (o.isMesh) o.material = new THREE.MeshStandardMaterial({ color: '#8fa3c7', roughness: 0.8 }); });
  return <ShoeModel scene={scene} {...rest} />;
};

export default function FloorShoe({ item, onError, onSelect, onHover, ...rest }) {
  const Loader = item.ext === 'obj' ? ObjShoe : GlbShoe;
  return (
    <SkipOnError onError={() => onError(item.id)}>
      <Suspense fallback={null}>
        <Loader url={item.url} onSelect={() => onSelect(item.id)} onHover={(on) => onHover(on ? item.id : null)} {...rest} />
      </Suspense>
    </SkipOnError>
  );
}
