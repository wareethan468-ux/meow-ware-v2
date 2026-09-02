import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';

const preserveDownload = () => ({
  name: 'preserve-download',
  closeBundle() {
    const output = resolve('dist/Meow-Ware-v1.3.exe');
    if (!existsSync(output)) {
      mkdirSync(resolve('dist'), { recursive: true });
      copyFileSync(resolve('public/Meow-Ware-v1.3.exe'), output);
    }
  },
});

export default defineConfig({
  plugins: [react(), preserveDownload()],
  publicDir: false,
  server: {
    watch: { ignored: ['**/*.exe'] },
  },
  build: { outDir: 'dist', emptyOutDir: false },
});
