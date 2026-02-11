import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Charger les variables d'environnement depuis le fichier .env à la racine
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    base: '/GuitarHunter/',
    define: {
      // On expose explicitement APP_ID_TARGET et USER_ID_TARGET au code frontend
      'process.env.APP_ID_TARGET': JSON.stringify(env.APP_ID_TARGET),
      'process.env.USER_ID_TARGET': JSON.stringify(env.USER_ID_TARGET)
    }
  }
})
