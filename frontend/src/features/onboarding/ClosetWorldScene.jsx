import { Suspense, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { ContactShadows, Float } from '@react-three/drei';
import { Shape } from 'three';

const shirtShape = new Shape();
shirtShape.moveTo(-0.3, 0.48);
shirtShape.lineTo(-0.12, 0.32);
shirtShape.lineTo(-0.05, 0.39);
shirtShape.lineTo(0.05, 0.39);
shirtShape.lineTo(0.12, 0.32);
shirtShape.lineTo(0.3, 0.48);
shirtShape.lineTo(0.48, 0.27);
shirtShape.lineTo(0.36, 0.14);
shirtShape.lineTo(0.28, 0.2);
shirtShape.lineTo(0.28, -0.5);
shirtShape.lineTo(-0.28, -0.5);
shirtShape.lineTo(-0.28, 0.2);
shirtShape.lineTo(-0.36, 0.14);
shirtShape.lineTo(-0.48, 0.27);
shirtShape.closePath();

const railGarments = [
	{ x: -2.35, color: '#ad735d' },
	{ x: -1.18, color: '#c9b99a' },
	{ x: 0, color: '#687a68' },
	{ x: 1.18, color: '#a8879c' },
	{ x: 2.35, color: '#647b91' },
];

const cameraStops = [
	{ position: [0, 0.25, 9.5], target: [0, 0, 0] },
	{ position: [0, 0.15, -3.2], target: [0, 0, -12] },
	{ position: [-0.75, 1.1, -13.1], target: [-0.75, 0.9, -24] },
	{ position: [0, 0.2, -27.1], target: [0, 0, -36] },
	{ position: [0, 0.2, -40], target: [0, 0, -48] },
];

function ClosetSet({ build, compact }) {
	const leftWall = useRef(null);
	const rightWall = useRef(null);
	const header = useRef(null);
	const base = useRef(null);
	const backPanel = useRef(null);

	useFrame(() => {
		const progress = Math.min(1, build.current);
		const eased = 1 - (1 - progress) ** 3;
		if (leftWall.current) leftWall.current.scale.y = eased;
		if (rightWall.current) rightWall.current.scale.y = eased;
		if (header.current) header.current.scale.x = eased;
		if (base.current) base.current.scale.x = eased;
		if (backPanel.current) backPanel.current.scale.y = eased;
	});

	return (
		<group position={[0, 0, 0]}>
			<mesh ref={backPanel} position={[0, 0, -0.35]}>
				<boxGeometry args={[6.3, 5.2, 0.2]} />
				<meshStandardMaterial color="#26251f" roughness={0.88} />
			</mesh>
			<mesh ref={leftWall} position={[-3.05, 0, 0]}>
				<boxGeometry args={[0.2, 5.3, 1.05]} />
				<meshStandardMaterial color="#665541" roughness={0.4} />
			</mesh>
			<mesh ref={rightWall} position={[3.05, 0, 0]}>
				<boxGeometry args={[0.2, 5.3, 1.05]} />
				<meshStandardMaterial color="#665541" roughness={0.4} />
			</mesh>
			<mesh ref={header} position={[0, 2.55, 0]}>
				<boxGeometry args={[6.3, 0.2, 1.05]} />
				<meshStandardMaterial color="#806a4d" roughness={0.38} />
			</mesh>
			<mesh ref={base} position={[0, -2.55, 0]}>
				<boxGeometry args={[6.3, 0.2, 1.05]} />
				<meshStandardMaterial color="#806a4d" roughness={0.38} />
			</mesh>
			<mesh position={[0, 0.55, 0.17]}>
				<cylinderGeometry args={[0.045, 0.045, 5.4, 20]} />
				<meshStandardMaterial color="#d2b88e" metalness={0.68} roughness={0.28} />
			</mesh>
			{railGarments.map((garment, index) => (
				<Garment key={`closet-${garment.x}`} color={garment.color} index={index} position={[compact ? (index - 2) * 0.67 : garment.x * 0.68, 0.08, 0.22]} size={compact ? 0.6 : 0.72} />
			))}
			<mesh position={[0, -2.15, 0.35]}>
				<boxGeometry args={[6.15, 0.68, 0.8]} />
				<meshStandardMaterial color="#4a3e30" roughness={0.52} />
			</mesh>
			<mesh position={[-1.85, -1.95, 0.78]}>
				<boxGeometry args={[1.15, 0.16, 0.32]} />
				<meshStandardMaterial color="#ad8c62" roughness={0.42} />
			</mesh>
			<mesh position={[0, -1.95, 0.78]}>
				<boxGeometry args={[1.15, 0.16, 0.32]} />
				<meshStandardMaterial color="#ad8c62" roughness={0.42} />
			</mesh>
			<mesh position={[1.85, -1.95, 0.78]}>
				<boxGeometry args={[1.15, 0.16, 0.32]} />
				<meshStandardMaterial color="#ad8c62" roughness={0.42} />
			</mesh>
		</group>
	);
}

function Garment({ position, color, index = 0, entering = false, added, size = 0.94 }) {
	const ref = useRef(null);
	const delay = index * 0.22;

	useFrame(({ clock }) => {
		if (!ref.current) return;
		const time = clock.elapsedTime;
		ref.current.rotation.z = Math.sin(time * 0.48 + delay) * 0.018;
		if (entering) {
			const amount = Math.min(1, added.current);
			const eased = 1 - (1 - amount) ** 3;
			ref.current.position.y = position[1] - (1 - eased) * 2.4;
			ref.current.scale.setScalar(eased * 0.94);
		}
	});

	return (
		<group ref={ref} position={position} scale={entering ? 0.01 : size}>
			<mesh position={[0, -0.08, 0]} castShadow>
				<shapeGeometry args={[shirtShape, 20]} />
				<meshStandardMaterial color={color} roughness={0.82} side={2} />
			</mesh>
			<mesh position={[0, 0.54, 0]} rotation={[0, 0, Math.PI / 2]}>
				<torusGeometry args={[0.13, 0.014, 8, 24, Math.PI]} />
				<meshStandardMaterial color="#d8c8a9" metalness={0.4} roughness={0.42} />
			</mesh>
			<mesh position={[0, 0.45, 0]} rotation={[0, 0, Math.PI / 2]}>
				<cylinderGeometry args={[0.012, 0.012, 0.18, 8]} />
				<meshStandardMaterial color="#d8c8a9" metalness={0.4} roughness={0.42} />
			</mesh>
		</group>
	);
}

function HangerRail({ hasClothing, added, compact }) {
	return (
		<group position={[0, 0, -36]}>
			<mesh position={[0, 0.55, 0]} rotation={[0, 0, Math.PI / 2]}>
				<cylinderGeometry args={[0.055, 0.055, compact ? 5.2 : 7.8, 20]} />
				<meshStandardMaterial color="#c5a77d" metalness={0.68} roughness={0.25} />
			</mesh>
			{railGarments.map((garment, index) => (
				<Garment key={garment.x} color={garment.color} index={index} position={[compact ? (index - 2) * 0.7 : garment.x, 0.05, 0.1]} size={compact ? 0.68 : 0.94} />
			))}
			{hasClothing && <Garment added={added} color="#c49372" entering index={6} position={[compact ? 2.1 : 3.35, 0.05, 0.38]} size={compact ? 0.64 : 0.88} />}
			<mesh position={[0, -2.05, -0.15]}>
				<boxGeometry args={[compact ? 5.3 : 7.6, 0.16, 1.15]} />
				<meshStandardMaterial color="#544637" roughness={0.5} />
			</mesh>
		</group>
	);
}

function Mirror({ portrait }) {
	return (
		<group position={[0, 0, -12]}>
			<mesh position={[0, 0.18, -0.12]}>
				<boxGeometry args={[3.5, 5.7, 0.34]} />
				<meshStandardMaterial color="#6e5945" roughness={0.36} metalness={0.15} />
			</mesh>
			<mesh position={[0, 0.18, 0.08]}>
				<boxGeometry args={[3.14, 5.32, 0.08]} />
				<meshStandardMaterial color="#303333" roughness={0.16} metalness={0.72} emissive="#293333" emissiveIntensity={0.24} />
			</mesh>
			<mesh position={[0, -2.83, 0.2]}>
				<boxGeometry args={[2.8, 0.12, 0.44]} />
				<meshStandardMaterial color="#8a7153" roughness={0.42} />
			</mesh>
			{portrait && <mesh position={[0, 0.2, 0.22]}>
				<planeGeometry args={[2.75, 4.95]} />
				<meshBasicMaterial color="#5d6460" transparent opacity={0.42} />
			</mesh>}
			<Float speed={0.8} rotationIntensity={0.08} floatIntensity={0.12} position={[-2.25, 1.5, 0.25]}>
				<mesh><sphereGeometry args={[0.14, 24, 24]} /><meshStandardMaterial color="#c49372" emissive="#c49372" emissiveIntensity={0.45} /></mesh>
			</Float>
		</group>
	);
}

function FittingMannequin({ bodyPhoto }) {
	return (
		<group position={[0, -1.8, -24]}>
			<mesh position={[0, -0.14, -0.35]} receiveShadow>
				<cylinderGeometry args={[2.15, 2.3, 0.28, 48]} />
				<meshStandardMaterial color="#514637" roughness={0.55} />
			</mesh>
			<mesh position={[0, 0.02, -0.33]}>
				<cylinderGeometry args={[1.9, 2.1, 0.06, 48]} />
				<meshStandardMaterial color="#b08b61" roughness={0.42} metalness={0.1} />
			</mesh>
			<group position={[0, 0.12, 0]}>
				<mesh castShadow position={[0, 3.28, 0]} scale={[0.46, 0.55, 0.4]}>
					<sphereGeometry args={[1, 32, 24]} />
					<meshStandardMaterial color={bodyPhoto ? '#bc957b' : '#aa927d'} roughness={0.66} />
				</mesh>
				<mesh castShadow position={[0, 2.84, 0]}>
					<cylinderGeometry args={[0.15, 0.19, 0.38, 24]} />
					<meshStandardMaterial color="#aa927d" roughness={0.68} />
				</mesh>
				<mesh castShadow position={[0, 1.95, 0]} scale={[1, 1, 0.78]}>
					<capsuleGeometry args={[0.52, 0.8, 8, 20]} />
					<meshStandardMaterial color="#6c7d70" roughness={0.78} />
				</mesh>
				<mesh castShadow position={[-0.65, 1.96, 0]} rotation={[0, 0, -0.1]}>
					<capsuleGeometry args={[0.15, 0.83, 8, 16]} />
					<meshStandardMaterial color="#aa927d" roughness={0.72} />
				</mesh>
				<mesh castShadow position={[0.65, 1.96, 0]} rotation={[0, 0, 0.1]}>
					<capsuleGeometry args={[0.15, 0.83, 8, 16]} />
					<meshStandardMaterial color="#aa927d" roughness={0.72} />
				</mesh>
				<mesh castShadow position={[0, 0.9, 0]}>
					<cylinderGeometry args={[0.43, 0.38, 0.58, 24]} />
					<meshStandardMaterial color="#66564d" roughness={0.8} />
				</mesh>
				{[-0.22, 0.22].map((x) => <group key={x}>
					<mesh castShadow position={[x, 0.22, 0]}><cylinderGeometry args={[0.19, 0.14, 1.0, 20]} /><meshStandardMaterial color="#66564d" roughness={0.8} /></mesh>
					<mesh castShadow position={[x, -0.34, 0.12]}><boxGeometry args={[0.34, 0.15, 0.52]} /><meshStandardMaterial color="#b8aa91" roughness={0.63} /></mesh>
				</group>)}
			</group>
			<mesh position={[0, 4.45, 0]}><torusGeometry args={[0.13, 0.025, 8, 20]} /><meshStandardMaterial color="#d3b88f" metalness={0.55} roughness={0.28} /></mesh>
			<ContactShadows position={[0, -0.01, 0]} opacity={0.32} scale={5} blur={2.5} far={4} />
		</group>
	);
}

function Room({ progress, hasClothing, hasPortrait, hasBodyPhoto, pointer }) {
	const { size } = useThree();
	const closetBuild = useRef(0);
	const rack = useRef(null);
	const added = useRef(0);
	const currentTarget = useRef(null);

	useFrame(({ clock, camera }, delta) => {
		const compact = size.width < 760;
		const cameraFov = compact ? 56 : 40;
		if (camera.fov !== cameraFov) {
			camera.fov = cameraFov;
			camera.updateProjectionMatrix();
		}
		closetBuild.current = Math.min(1, closetBuild.current + delta * 0.52);
		if (hasClothing) added.current = Math.min(1, added.current + delta * 1.2);
		else added.current = 0;

		const value = Math.max(0, Math.min(0.9999, progress.current)) * (cameraStops.length - 1);
		const segment = Math.floor(value);
		const amount = value - segment;
		const from = cameraStops[segment];
		const to = cameraStops[segment + 1];
		const eased = amount * amount * (3 - 2 * amount);
		const nextPosition = [0, 1, 2].map((axis) => from.position[axis] + (to.position[axis] - from.position[axis]) * eased);
		const nextTarget = [0, 1, 2].map((axis) => from.target[axis] + (to.target[axis] - from.target[axis]) * eased);
		nextPosition[0] += pointer.current.x * 0.3;
		nextPosition[1] -= pointer.current.y * 0.16;
		const spring = 1 - Math.exp(-delta * 2.7);
		camera.position.lerp({ x: nextPosition[0], y: nextPosition[1], z: nextPosition[2] }, spring);
		currentTarget.current ??= camera.position.clone();
		currentTarget.current.lerp({ x: nextTarget[0], y: nextTarget[1], z: nextTarget[2] }, spring);
		camera.lookAt(currentTarget.current);
		if (rack.current) rack.current.rotation.y = Math.sin(clock.elapsedTime * 0.22) * 0.025;
	});

	return (
		<>
			<ambientLight intensity={1.05} />
			<hemisphereLight color="#d9c8a7" groundColor="#211d19" intensity={1.1} />
			<directionalLight castShadow position={[4, 8, 5]} intensity={2.5} />
			<pointLight position={[-3, 2, -10]} color="#c08e69" intensity={22} distance={13} />
			<pointLight position={[3, 2, -22]} color="#8f9e8a" intensity={20} distance={13} />
			<pointLight position={[-3, 2, -35]} color="#c59c77" intensity={19} distance={14} />
			<mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.9, -21]} receiveShadow>
				<planeGeometry args={[9, 57]} />
				<meshStandardMaterial color="#25221d" roughness={0.95} />
			</mesh>
			<ClosetSet build={closetBuild} compact={size.width < 760} />
			<Mirror portrait={hasPortrait} />
			<FittingMannequin bodyPhoto={hasBodyPhoto} />
			<group ref={rack}>
				<HangerRail added={added} compact={size.width < 760} hasClothing={hasClothing} />
			</group>
			<ClosetBuildRail build={closetBuild} />
		</>
	);
}

function ClosetBuildRail({ build }) {
	const rail = useRef(null);
	useFrame(() => {
		if (rail.current) rail.current.scale.x = Math.min(1, build.current);
	});
	return (
		<group ref={rail} position={[0, 0, -36]}>
			<mesh position={[-3.7, 2.2, 0]}><boxGeometry args={[0.18, 4.5, 0.2]} /><meshStandardMaterial color="#705b42" /></mesh>
			<mesh position={[3.7, 2.2, 0]}><boxGeometry args={[0.18, 4.5, 0.2]} /><meshStandardMaterial color="#705b42" /></mesh>
			<mesh position={[0, 4.38, 0]}><boxGeometry args={[7.6, 0.18, 0.2]} /><meshStandardMaterial color="#987650" /></mesh>
		</group>
	);
}

export default function ClosetWorldScene({ progress, hasClothing, hasPortrait, hasBodyPhoto, pointer }) {
	return (
		<Canvas camera={{ position: [0, 0.25, 9.5], fov: 40 }} dpr={[1, 1.5]} shadows gl={{ antialias: true, alpha: true }} fallback={<div className="onboarding-canvas-fallback" />}>
			<Suspense fallback={null}>
				<Room progress={progress} hasClothing={hasClothing} hasPortrait={hasPortrait} hasBodyPhoto={hasBodyPhoto} pointer={pointer} />
			</Suspense>
		</Canvas>
	);
}
