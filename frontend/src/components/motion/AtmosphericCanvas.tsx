/**
 * High-End Interactive WebGL Atmospheric Engine — v2
 *
 * Upgrades from the original torus-knot wireframe to:
 * - A glowing glass Icosahedron (MeshPhysicalMaterial, no wireframe)
 * - Emissive edge-highlight ring (EdgesGeometry in neon indigo)
 * - 8 orbiting neon orbs that circle the icosahedron like planets
 * - Neon accent lighting (indigo + racing lime + cyan RectAreaLight)
 * - Spring-damped mouse tracking preserved
 * - 1,800-particle starfield preserved
 */
import { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

// ── Orbiting orbs ────────────────────────────────────────────────────────────

const ORB_COLORS = ["#6366f1", "#D2FF00", "#4cc9f0", "#8b5cf6", "#D2FF00", "#6366f1", "#4cc9f0", "#8b5cf6"];
const ORB_COUNT = 8;

function OrbitingOrbs() {
  const groupRef = useRef<THREE.Group>(null!);
  const orbRefs = useRef<THREE.Mesh[]>([]);
  const pointer = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const still = useRef(false);

  const orbs = useMemo(() =>
    Array.from({ length: ORB_COUNT }, (_, i) => ({
      angle: (i / ORB_COUNT) * Math.PI * 2,
      radius: 2.2 + (i % 3) * 0.25,
      height: Math.sin((i / ORB_COUNT) * Math.PI * 2) * 0.5,
      speed: 0.28 + i * 0.04,
      size: 0.055 + (i % 3) * 0.025,
      color: ORB_COLORS[i],
    })), []);

  useEffect(() => {
    still.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const m = (e: MouseEvent) => {
      pointer.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", m, { passive: true });
    return () => window.removeEventListener("mousemove", m);
  }, []);

  useFrame((state) => {
    if (still.current) return;
    pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.04;
    pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.04;

    const t = state.clock.getElapsedTime();
    orbs.forEach((orb, i) => {
      const mesh = orbRefs.current[i];
      if (!mesh) return;
      const a = orb.angle + t * orb.speed + pointer.current.x * 0.3;
      mesh.position.x = Math.cos(a) * orb.radius;
      mesh.position.z = Math.sin(a) * orb.radius;
      mesh.position.y = orb.height + Math.sin(t * 0.6 + i) * 0.18;
      // subtle scale pulse
      const scale = 1 + Math.sin(t * 1.4 + i * 0.9) * 0.18;
      mesh.scale.setScalar(scale);
    });

    if (groupRef.current) {
      groupRef.current.rotation.y += 0.002 + pointer.current.x * 0.005;
      groupRef.current.rotation.x = pointer.current.y * 0.12;
    }
  });

  return (
    <group ref={groupRef} position={[2.5, 0.2, -1]}>
      {orbs.map((orb, i) => (
        <mesh key={i} ref={(el) => { if (el) orbRefs.current[i] = el; }}>
          <sphereGeometry args={[orb.size, 8, 8]} />
          <meshStandardMaterial
            color={orb.color}
            emissive={orb.color}
            emissiveIntensity={2.2}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  );
}

// ── Glowing Icosahedron ───────────────────────────────────────────────────────

function GlowIcosahedron() {
  const meshRef  = useRef<THREE.Mesh>(null!);
  const edgesRef = useRef<THREE.LineSegments>(null!);
  const pointer  = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const still    = useRef(false);

  const edgesGeo = useMemo(() => {
    const geo = new THREE.IcosahedronGeometry(1.55, 1);
    return new THREE.EdgesGeometry(geo);
  }, []);

  useEffect(() => {
    still.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const m = (e: MouseEvent) => {
      pointer.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", m, { passive: true });
    return () => window.removeEventListener("mousemove", m);
  }, []);

  useFrame((state, delta) => {
    if (!meshRef.current || still.current) return;
    pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.04;
    pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.04;

    meshRef.current.rotation.x  += delta * 0.12 + pointer.current.y * 0.018;
    meshRef.current.rotation.y  += delta * 0.18 + pointer.current.x * 0.018;
    meshRef.current.rotation.z  += delta * 0.04;

    if (edgesRef.current) {
      edgesRef.current.rotation.copy(meshRef.current.rotation);
    }

    // Organic breathing
    const t = state.clock.getElapsedTime();
    const s = 1 + Math.sin(t * 0.7) * 0.05;
    meshRef.current.scale.setScalar(s);
    if (edgesRef.current) edgesRef.current.scale.setScalar(s * 1.002);
  });

  return (
    <group position={[2.5, 0.2, -1]}>
      {/* Inner glass body */}
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.55, 1]} />
        <meshPhysicalMaterial
          color="#1a1a3a"
          emissive="#4338ca"
          emissiveIntensity={0.35}
          transparent
          opacity={0.22}
          roughness={0.05}
          metalness={0.1}
          transmission={0.7}
          thickness={1.2}
          ior={1.5}
          side={THREE.DoubleSide}
        />
      </mesh>
      {/* Neon edges */}
      <lineSegments ref={edgesRef} geometry={edgesGeo}>
        <lineBasicMaterial
          color="#7b5cff"
          transparent
          opacity={0.75}
          toneMapped={false}
        />
      </lineSegments>
    </group>
  );
}

// ── Particle field ────────────────────────────────────────────────────────────

function ParticleGrid({ count = 1800 }: { count?: number }) {
  const pointsRef = useRef<THREE.Points>(null!);
  const pointer   = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const still     = useRef(false);

  const [positions, initialPositions, colors] = useMemo(() => {
    const pos  = new Float32Array(count * 3);
    const cols = new Float32Array(count * 3);
    const c1 = new THREE.Color("#6366F1");
    const c2 = new THREE.Color("#D2FF00");
    const c3 = new THREE.Color("#00F5A0");

    for (let i = 0; i < count; i++) {
      pos[i * 3]     = (Math.random() - 0.5) * 16;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 10;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 8;
      const pick = Math.random();
      const col  = pick > 0.85 ? c2 : pick > 0.65 ? c3 : c1;
      cols[i * 3]     = col.r;
      cols[i * 3 + 1] = col.g;
      cols[i * 3 + 2] = col.b;
    }
    return [pos, new Float32Array(pos), cols];
  }, [count]);

  useEffect(() => {
    still.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const m = (e: MouseEvent) => {
      pointer.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", m, { passive: true });
    return () => window.removeEventListener("mousemove", m);
  }, []);

  useFrame((state, delta) => {
    if (!pointsRef.current || still.current) return;
    pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.05;
    pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.05;

    pointsRef.current.rotation.y += delta * 0.04 + pointer.current.x * 0.01;
    pointsRef.current.rotation.x  = pointer.current.y * 0.15;

    const arr  = pointsRef.current.geometry.attributes.position.array as Float32Array;
    const time = state.clock.getElapsedTime();
    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      arr[i3 + 1] = initialPositions[i3 + 1] + Math.sin(time * 0.7 + initialPositions[i3] * 0.6) * 0.25;
      arr[i3]     = initialPositions[i3]     + Math.cos(time * 0.5 + initialPositions[i3 + 2] * 0.4) * 0.15;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color"    args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.038}
        vertexColors
        transparent
        opacity={0.65}
        blending={THREE.AdditiveBlending}
        depthWrite={false}
      />
    </points>
  );
}

// ── Export ────────────────────────────────────────────────────────────────────

export function AtmosphericCanvas() {
  return (
    <div className="absolute inset-0 -z-10 pointer-events-none" style={{ opacity: 0.85, overflow: "hidden" }}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 5.5], fov: 55 }}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      >
        <ambientLight intensity={0.4} />
        <pointLight position={[4,  6,  4]}  intensity={2.5}  color="#6366F1" />
        <pointLight position={[-4, -4, -3]} intensity={1.8}  color="#D2FF00" />
        <pointLight position={[0,  8,  2]}  intensity={1.2}  color="#4cc9f0" />
        <GlowIcosahedron />
        <OrbitingOrbs />
        <ParticleGrid />
      </Canvas>
    </div>
  );
}

export default AtmosphericCanvas;
