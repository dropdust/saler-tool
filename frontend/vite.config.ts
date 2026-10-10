/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 开发模式：代理到本地后端（默认 8620）
    proxy: {
      '/api': { target: 'http://127.0.0.1:8620', changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts'],
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
