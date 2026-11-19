import React, { useEffect, useRef } from 'react';

import type { LiveVoiceLevels } from './usePipecatVoiceSession';

export type RibbonMood = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'muted' | 'ended' | 'error';

interface RibbonStyle {
  /** Resting height of the ribbon (fraction of the canvas height). */
  rest: number;
  /** How fast it flows. */
  speed: number;
  /** Prismatic fringe colours, drawn additively around a white core. */
  colors: string[];
  glow: number;
}

const PRISM = ['#64d2ff', '#ff9f0a', '#ff6482', '#bf5af2'];
const STYLES: Record<RibbonMood, RibbonStyle> = {
  idle: { rest: 0.14, speed: 0.35, colors: PRISM, glow: 0.55 },
  connecting: { rest: 0.08, speed: 1.4, colors: PRISM, glow: 0.5 },
  listening: { rest: 0.15, speed: 0.6, colors: PRISM, glow: 0.75 },
  thinking: { rest: 0.17, speed: 2.2, colors: ['#bf5af2', '#5e5ce6', '#64d2ff', '#ff6482'], glow: 0.85 },
  speaking: { rest: 0.16, speed: 1.1, colors: PRISM, glow: 1 },
  muted: { rest: 0.04, speed: 0.25, colors: ['#8e8e93', '#636366', '#8e8e93', '#aeaeb2'], glow: 0.3 },
  ended: { rest: 0.05, speed: 0.25, colors: PRISM, glow: 0.35 },
  error: { rest: 0.06, speed: 0.4, colors: ['#ff453a', '#ff9f0a', '#ff375f', '#ff453a'], glow: 0.5 },
};

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)').matches);
}

/** One lens-shaped band: tapered at both ends, swelling with a travelling wave. */
function band(
  ctx: CanvasRenderingContext2D,
  width: number,
  mid: number,
  height: number,
  phase: number,
  frequency: number,
  skew: number,
) {
  const steps = 64;
  const top: Array<[number, number]> = [];
  const bottom: Array<[number, number]> = [];
  for (let i = 0; i <= steps; i += 1) {
    const u = i / steps;
    const taper = Math.exp(-(((u - 0.5) / 0.26) ** 2));
    const wave = Math.sin(u * Math.PI * frequency + phase);
    const centre = mid + wave * height * 0.55 * taper + skew * (u - 0.5) * height;
    const thickness = height * taper * (0.35 + 0.65 * (0.5 + 0.5 * Math.sin(u * 5 + phase * 0.7)));
    top.push([u * width, centre - thickness / 2]);
    bottom.push([u * width, centre + thickness / 2]);
  }
  ctx.beginPath();
  top.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
  bottom.reverse().forEach(([x, y]) => ctx.lineTo(x, y));
  ctx.closePath();
}

/**
 * Manifest's voice as a ribbon of light, in the spirit of Apple's Siri: a white core with a
 * prismatic fringe that flows slowly at rest and swells with whoever is speaking.
 */
const VoiceRibbon: React.FC<{ mood: RibbonMood; levelsRef: React.MutableRefObject<LiveVoiceLevels> }> = ({
  mood,
  levelsRef,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const moodRef = useRef(mood);
  moodRef.current = mood;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return undefined;
    const still = prefersReducedMotion();
    let frame = 0;
    let energy = 0;
    let time = 0;
    let last = performance.now();

    const draw = (now: number) => {
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
      }
      const style = STYLES[moodRef.current];
      const levels = levelsRef.current;
      const live = moodRef.current === 'listening' || moodRef.current === 'speaking' || moodRef.current === 'thinking';
      const target = live ? Math.min(1, Math.max(levels.bot, levels.mic * 0.8) * 2.4) : 0;
      energy += (target - energy) * 0.12;
      time += ((now - last) / 1000) * style.speed * (1 + energy * 1.5);
      last = now;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.globalCompositeOperation = 'lighter';
      const mid = h / 2;
      const height = h * (style.rest + energy * 0.42);

      // Prismatic fringe: blurred colour bands, each slightly out of phase.
      style.colors.forEach((color, index) => {
        ctx.filter = `blur(${7 + index * 2}px)`;
        ctx.globalAlpha = 0.55 * style.glow;
        ctx.fillStyle = color;
        band(ctx, w, mid + (index - 1.5) * 2.5, height * (1.15 - index * 0.06), time * (1 + index * 0.13) + index, 2.2 + index * 0.35, index % 2 ? 0.25 : -0.25);
        ctx.fill();
      });
      // White core: two crisp, bright strands.
      ctx.filter = 'blur(1.5px)';
      ctx.globalAlpha = 0.9;
      const core = ctx.createLinearGradient(0, 0, w, 0);
      core.addColorStop(0, 'rgba(255,255,255,0)');
      core.addColorStop(0.5, 'rgba(255,255,255,1)');
      core.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = core;
      band(ctx, w, mid, height * 0.42, time * 1.1 + 0.6, 2.4, 0.15);
      ctx.fill();
      ctx.globalAlpha = 0.6;
      band(ctx, w, mid + 1, height * 0.28, time * 0.9 + 2.2, 1.9, -0.2);
      ctx.fill();
      ctx.filter = 'none';
      ctx.globalAlpha = 1;
      ctx.globalCompositeOperation = 'source-over';

      if (!still) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [levelsRef]);

  return <canvas aria-hidden="true" className="lv-ribbon" ref={canvasRef} />;
};

export default VoiceRibbon;
