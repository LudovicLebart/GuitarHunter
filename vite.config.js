import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Charger les variables d'environnement depuis le fichier .env à la racine
  // Le 3ème argument '' permet de charger toutes les variables, pas seulement celles préfixées par VITE_
  const env = loadEnv(mode, process.cwd(), '');

  return {
    plugins: [react()],
    base: '/GuitarHunter/',
    define: {
      // On expose explicitement APP_ID_TARGET au code frontend
      'process.env.APP_ID_TARGET': JSON.stringify(env.APP_ID_TARGET)
    }
  }
})
