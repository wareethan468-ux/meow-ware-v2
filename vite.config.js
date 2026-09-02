import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    watch: {
      ignored: ['**/build/**', '**/dist/**', '**/src/gui/ui/react/**'],
    },
  },
  build: {
    outDir: resolve(import.meta.dirname, 'src/gui/ui/react'),
    emptyOutDir: true,
  },
});
