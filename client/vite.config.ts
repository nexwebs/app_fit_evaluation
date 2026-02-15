import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 4321
  },
  preview: {
    host: '0.0.0.0',
    port: 10000,
    allowedHosts: [
      'app-fit-evaluation-1.onrender.com',
      'localhost'
    ]
  }
})