import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],

  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          // React and the router change far less often than the app, so they get
          // their own chunk the browser keeps cached across deploys. Pages are
          // split by the lazy imports in App.tsx (react-markdown goes with the
          // summary pages that use it).
          groups: [{ name: 'react-vendor', test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/ }],
        },
      },
    },
  },

  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})