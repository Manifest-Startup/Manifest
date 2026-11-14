#!/usr/bin/env node
// Guard: heavy lazy-only chunks must never be referenced from the built
// index.html (script src, modulepreload, or stylesheet). size-limit alone
// cannot catch this — it sums named chunk patterns and misses a regression
// where e.g. pdf.js or TipTap get wired into the boot graph (this happened
// with rolldown's manualChunks dependency capture; see vite.config.ts).
//
// Usage: node scripts/check-boot-chunks.mjs  (run after `vite build`)
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const HEAVY_LAZY_CHUNKS = ['pdf', 'editor', 'pptx', 'hls', 'analytics'];

const htmlPath = resolve(dirname(fileURLToPath(import.meta.url)), '../build/index.html');
const html = readFileSync(htmlPath, 'utf8');

const referenced = [...html.matchAll(/assets\/([A-Za-z0-9_.-]+?)-[A-Za-z0-9_-]+\.(?:js|css)/g)].map(
  (m) => m[1],
);

const offenders = HEAVY_LAZY_CHUNKS.filter((name) => referenced.includes(name));

if (offenders.length > 0) {
  console.error(
    `check-boot-chunks: FAIL — lazy-only chunk(s) referenced from index.html boot path: ${offenders.join(', ')}\n` +
      'These must load on demand, not at boot. Check vite.config.ts codeSplitting groups.',
  );
  process.exit(1);
}

console.log(
  `check-boot-chunks: OK — boot path references [${[...new Set(referenced)].join(', ')}]; ` +
    `none of [${HEAVY_LAZY_CHUNKS.join(', ')}] present.`,
);
