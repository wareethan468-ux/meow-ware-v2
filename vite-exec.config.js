import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// __dirname equivalent for ESM
const __dirname = dirname(fileURLToPath(import.meta.url));
// exec/ lives next to Roblox-Fastflag-Manager-main/ (one level up, then into exec/)
const execRoot = resolve(__dirname, '..', 'exec');
// node_modules lives inside Roblox-Fastflag-Manager-main/
const nm = resolve(__dirname, 'node_modules');

/**
 * Vite config for the standalone Executor React app.
 * Source root: ../exec/
 * Build output: ../exec/dist/
 *
 * Run dev:  npm run exec:dev
 * Build:    npm run exec:build
 */
export default defineConfig({
  plugins: [react()],
  root: execRoot,
  base: './',
  resolve: {
    alias: {
      // Alias bare module names to the shared node_modules so Rolldown
      // can find them even though exec/ has no node_modules of its own.
      'react': resolve(nm, 'react'),
      'react-dom': resolve(nm, 'react-dom'),
      'react/jsx-runtime': resolve(nm, 'react/jsx-runtime'),
      'react-dom/client': resolve(nm, 'react-dom/client'),
    },
  },
  server: {
    port: 5174,
    watch: {
      ignored: ['**/build/**', '**/dist/**', '**/src/gui/ui/react/**'],
    },
  },
  build: {
    outDir: resolve(execRoot, 'dist'),
    emptyOutDir: true,
  },
});
