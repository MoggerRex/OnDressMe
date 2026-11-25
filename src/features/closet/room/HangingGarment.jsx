import { Component, Suspense, useMemo, useRef } from 'react';
import { useFrame, useLoader } from '@react-three/fiber';
import { OBJLoader } from 'three/examples/jsm/loaders/OBJLoader.js';
import { useGLTF } from '@react-three/drei';
import * as THREE from 'three';

const TARGET_HEIGHT = 0.8; // metros; normaliza cualquier GLB a tamaño de camisa
const PUSH_RADIUS = 0.8;

// Una GLB inválida no debe tumbar todo el canvas: simplemente se quita.
class SkipOnError extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onError(); }
  render() { return this.state.failed ? null : this.props.children; }
}

function HangingModel({ scene, railY, rot, player }) {
  const pivot = useRef();
  const state = useRef({ ax: 0, az: 0, vx: 0.9, vz: 0.4 }); // golpe inicial: se ve viva al colgarla
  const uniforms = useMemo(
    () => ({ uTime: { value: 0 }, uAmp: { value: 0.01 }, uTop: { value: railY }, uH: { value: TARGET_HEIGHT }, uInv: { value: 1 } }),
    [railY],
  );

  const model = useMemo(() => {
    const m = scene.clone(true);
    const size = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
    const scale = TARGET_HEIGHT / (size.y || 1);
    m.scale.setScalar(scale);
    uniforms.uInv.value = 1 / scale;
    // la parte superior central queda en el origen (el gancho)
    const nb = new THREE.Box3().setFromObject(m);
    const c = nb.getCenter(new THREE.Vector3());
    m.position.set(-c.x, -nb.max.y, -c.z);
    m.traverse((o) => {
      if (!o.isMesh) return;
      const mat = o.material.clone();
      mat.side = THREE.DoubleSide;
      mat.onBeforeCompile = (s) => {
        Object.assign(s.uniforms, uniforms);
        s.vertexShader = s.vertexShader
          .replace('#include <common>', '#include <common>\nuniform float uTime,uAmp,uTop,uH,uInv;')
          .replace('#include <begin_vertex>', `#include <begin_vertex>
            float wy = (modelMatrix * vec4(position,1.0)).y;
            float h = clamp((uTop - wy) / uH, 0.0, 1.0);
            float k = h * h * uAmp * uInv;
            transformed.x += sin(uTime*3.0 + wy*9.0) * k;
            transformed.z += cos(uTime*2.3 + wy*7.0) * k;`);
      };
      o.material = mat;
    });
    return m;
  }, [scene, uniforms]);

  useFrame((fs, dt) => {
    dt = Math.min(dt, 0.05);
    const g = pivot.current;
    const s = state.current;
    const wp = g.getWorldPosition(new THREE.Vector3());
    const dx = wp.x - player.pos.x;
    const dz = wp.z - player.pos.z;
    const dist = Math.hypot(dx, dz);
    if (dist < PUSH_RADIUS && player.speed > 0.1) {
      // empuje alejándose del jugador, pasado al marco local de la prenda
      const f = ((PUSH_RADIUS - dist) / PUSH_RADIUS) * player.speed * 6 * dt;
      const nx = dx / (dist || 1), nz = dz / (dist || 1);
      const c = Math.cos(rot), sn = Math.sin(rot);
      const lx = nx * c - nz * sn, lz = nx * sn + nz * c;
      s.vx += -lz * f;
      s.vz += lx * f;
    }
    // péndulo amortiguado
    s.vx += (-30 * s.ax - 1.6 * s.vx) * dt; s.ax += s.vx * dt;
    s.vz += (-30 * s.az - 1.6 * s.vz) * dt; s.az += s.vz * dt;
    g.rotation.set(s.ax, 0, s.az);
    uniforms.uTime.value = fs.clock.elapsedTime;
    uniforms.uAmp.value = 0.012 + Math.min(0.1, (Math.abs(s.vx) + Math.abs(s.vz)) * 0.08);
  });

  return (
    <group ref={pivot}>
      <primitive object={model} />
      <mesh position={[0, 0.03, 0]}>
        <torusGeometry args={[0.04, 0.006, 6, 16]} />
        <meshStandardMaterial color="#b8b8c0" metalness={0.9} roughness={0.3} />
      </mesh>
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

export default function HangingGarment({ item, slot, player, onError }) {
  return (
    <group position={slot.position} rotation={[0, slot.rotY, 0]}>
      <SkipOnError onError={() => onError(item.id)}>
        <Suspense fallback={null}>
          {item.ext === 'obj' ? <ObjGarment url={item.url} railY={slot.position[1]} rot={slot.rotY} player={player} /> : <GlbGarment url={item.url} railY={slot.position[1]} rot={slot.rotY} player={player} />}
        </Suspense>
      </SkipOnError>
    </group>
  );
}
