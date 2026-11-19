import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react(), tsconfigPaths()],
    resolve: {
      alias: {
        process: 'process/browser',
      },
    },
    server: {
      host: '0.0.0.0',
      port: 3000,
      allowedHosts: true,
      proxy: {
        '/api': { target: 'http://localhost:8000', xfwd: true, ws: true },
        '/graphql': { target: 'http://localhost:8000', xfwd: true },
        '/generated': { target: 'http://localhost:8000', xfwd: true },
        '/socket.io': { target: 'http://localhost:8000', xfwd: true, ws: true },
        '^/auth/(login|logout|callback|me|status)$': { target: 'http://localhost:8000', xfwd: true },
        '^/auth/[^/]+/(start|callback|status)$': { target: 'http://localhost:8000', xfwd: true },
      },
    },
    preview: {
      host: '0.0.0.0',
      port: 3000,
    },
    build: {
      outDir: 'build',
      sourcemap: true,
      rollupOptions: {
        output: {
          // Vite 8 bundles with rolldown, whose `manualChunks` compatibility
          // shim recursively captures each group's dependencies. That capture
          // OVERRIDES explicit assignments: it dragged react/jsx-runtime and
          // clsx into the 'pdf' chunk and react itself into 'apollo', so
          // every page boot-loaded ~230KB gzip of pdf.js + TipTap. Use the
          // native codeSplitting API instead, with dependency capture off,
          // so each group holds exactly what its test matches and everything
          // else falls back to rolldown's automatic (graph-correct) chunking.
          //
          // strictExecutionOrder is rolldown's recommended companion to
          // includeDependenciesRecursively: false — it guarantees valid
          // cross-chunk module execution order, which is what protects
          // against the Apollo/rxjs "Class extends value undefined" blank
          // screen this config used to work around.
          codeSplitting: {
            includeDependenciesRecursively: false,
            groups: [
              {
                // Apollo + its runtime peer deps stay together so the rxjs
                // Subscriber/Observable classes Apollo extends at module-init
                // time always evaluate in the same chunk.
                name: 'apollo',
                priority: 100,
                test: /node_modules[\\/](@apollo|graphql|rxjs|tslib|@wry|optimism|zen-observable(-ts)?|symbol-observable|ts-invariant|hoist-non-react-statics|response-iterator)[\\/]/,
              },
              {
                name: 'react-vendor',
                priority: 90,
                test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler|use-sync-external-store)[\\/]/,
              },
              {
                name: 'editor',
                priority: 80,
                test: /node_modules[\\/](@tiptap|prosemirror-[^\\/]+|markdown-it|highlight\.js)[\\/]/,
              },
              {
                name: 'pdf',
                priority: 70,
                test: /node_modules[\\/](pdfjs-dist|react-pdf)[\\/]/,
              },
              {
                name: 'analytics',
                priority: 60,
                test: /node_modules[\\/]posthog/,
              },
            ],
          },
          strictExecutionOrder: true,
        },
      },
    },
    define: {
      'process.env.NODE_ENV': JSON.stringify(mode),
      'process.env.REACT_APP_PUBLIC_POSTHOG_KEY': JSON.stringify(
        env.REACT_APP_PUBLIC_POSTHOG_KEY ?? '',
      ),
      'process.env.REACT_APP_PUBLIC_POSTHOG_HOST': JSON.stringify(
        env.REACT_APP_PUBLIC_POSTHOG_HOST ?? '',
      ),
      'process.env.REACT_APP_GRAPHQL_URL': JSON.stringify(
        env.REACT_APP_GRAPHQL_URL ?? '',
      ),
      'process.env.REACT_APP_VERSION': JSON.stringify(
        env.REACT_APP_VERSION ?? '',
      ),
      'process.env.REACT_APP_SILENT_LOGGER': JSON.stringify(
        env.REACT_APP_SILENT_LOGGER ?? '',
      ),
      global: 'globalThis',
    },
  };
});
