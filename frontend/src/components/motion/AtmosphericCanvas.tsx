/**
 * High-End Interactive WebGL Atmospheric Engine.
 * Inspired by Lusion.co, LandoNorris.com, and Igloo.inc.
 *
 * Combines:
 * - A kinetic 3D organic wireframe torus knot (Lusion tech-craft aesthetic)
 * - 1,800 mouse-reactive starfield particles drifting with organic noise
 * - Spring-damped inertial cursor tracking & tilt
 * - Additive blending with electric indigo & racing neon accents
 */
import { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import * as THREE from "three";

function KineticHeroMesh() {
  const meshRef = useRef<THREE.Mesh>(null!);
  const pointer = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const still = useRef(false);

  useEffect(() => {
    still.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const handleMove = (e: MouseEvent) => {
      pointer.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", handleMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMove);
  }, []);

  useFrame((state, delta) => {
    if (!meshRef.current) return;
    if (still.current) return;

    pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.04;
    pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.04;

    meshRef.current.rotation.x += delta * 0.15 + pointer.current.y * 0.02;
    meshRef.current.rotation.y += delta * 0.2 + pointer.current.x * 0.02;
    meshRef.current.rotation.z += delta * 0.05;

    // Organic breathing scale
    const s = 1 + Math.sin(state.clock.getElapsedTime() * 0.8) * 0.06;
    meshRef.current.scale.set(s, s, s);
  });

  return (
    <group position={[2.5, 0.2, -1]}>
      <mesh ref={meshRef}>
        <torusKnotGeometry args={[1.5, 0.45, 128, 32, 2, 3]} />
        <meshStandardMaterial
          color="#6366F1"
          emissive="#4F46E5"
          emissiveIntensity={0.6}
          wireframe
          transparent
          opacity={0.35}
          roughness={0.2}
          metalness={0.8}
        />
      </mesh>
    </group>
  );
}

function ParticleGrid({ count = 1800 }: { count?: number }) {
  const pointsRef = useRef<THREE.Points>(null!);
  const pointer = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const still = useRef(false);

  const [positions, initialPositions, colors] = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const cols = new Float32Array(count * 3);
    const c1 = new THREE.Color("#6366F1");
    const c2 = new THREE.Color("#D2FF00"); // Racing lime
    const c3 = new THREE.Color("#00F5A0"); // Cyan

    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 16;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 10;
      pos[i * 3 + 2] = (Math.random() - 0.5) * 8;

      const pick = Math.random();
      const col = pick > 0.85 ? c2 : pick > 0.65 ? c3 : c1;
      cols[i * 3] = col.r;
      cols[i * 3 + 1] = col.g;
      cols[i * 3 + 2] = col.b;
    }
    return [pos, new Float32Array(pos), cols];
  }, [count]);

  useEffect(() => {
    still.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const handleMove = (e: MouseEvent) => {
      pointer.current.targetX = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.current.targetY = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", handleMove, { passive: true });
    return () => window.removeEventListener("mousemove", handleMove);
  }, []);

  useFrame((state, delta) => {
    if (!pointsRef.current) return;
    if (still.current) return;

    pointer.current.x += (pointer.current.targetX - pointer.current.x) * 0.05;
    pointer.current.y += (pointer.current.targetY - pointer.current.y) * 0.05;

    pointsRef.current.rotation.y += delta * 0.04 + pointer.current.x * 0.01;
    pointsRef.current.rotation.x = pointer.current.y * 0.15;

    const array = pointsRef.current.geometry.attributes.position.array as Float32Array;
    const time = state.clock.getElapsedTime();

    for (let i = 0; i < count; i++) {
      const i3 = i * 3;
      array[i3 + 1] = initialPositions[i3 + 1] + Math.sin(time * 0.7 + initialPositions[i3] * 0.6) * 0.25;
      array[i3] = initialPositions[i3] + Math.cos(time * 0.5 + initialPositions[i3 + 2] * 0.4) * 0.15;
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
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

export function AtmosphericCanvas() {
  return (
    <div className="absolute inset-0 -z-10 pointer-events-none" style={{ opacity: 0.85, overflow: "hidden" }}>
      <Canvas
        dpr={[1, 2]}
        camera={{ position: [0, 0, 5.5], fov: 55 }}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
      >
        <ambientLight intensity={0.5} />
        <pointLight position={[10, 10, 10]} intensity={1.2} color="#6366F1" />
        <pointLight position={[-10, -10, -5]} intensity={0.8} color="#D2FF00" />
        <KineticHeroMesh />
        <ParticleGrid />
      </Canvas>
    </div>
  );
}

export default AtmosphericCanvas;
