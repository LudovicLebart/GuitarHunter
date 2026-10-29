import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BASE = '/GuitarHunter/'
const FICHE_IMAGES = fileURLToPath(new URL('./docs/fiches/img', import.meta.url))
const IMAGE_TYPES = { '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif', '.svg': 'image/svg+xml' }

// Images des fiches techniques de restauration (docs/fiches/img/<slug>/…) : copiées au build dans `dist/fiches/img`
// (seul `dist/` part sur GitHub Pages, l'API ne sert aucun fichier) et servies telles quelles en développement.
// Une fiche y fait référence par un chemin relatif `img/<slug>/01-nom.jpg` (voir src/utils/fiches.js::resolveFicheImage).
const ficheImages = () => {
  let outDir = 'dist'
  return {
    name: 'fiche-images',
    configResolved(config) { outDir = path.resolve(config.root, config.build.outDir) },
    closeBundle() {
      if (fs.existsSync(FICHE_IMAGES)) fs.cpSync(FICHE_IMAGES, path.join(outDir, 'fiches', 'img'), { recursive: true })
    },
    configureServer(server) {
      server.middlewares.use(`${BASE}fiches/img`, (req, res, next) => {
        const file = path.join(FICHE_IMAGES, decodeURIComponent((req.url || '/').split('?')[0]))
        const type = IMAGE_TYPES[path.extname(file).toLowerCase()]
        // jamais en dehors du dossier des images, jamais autre chose qu'une image
        if (!type || !file.startsWith(FICHE_IMAGES + path.sep) || !fs.existsSync(file)) return next()
        res.setHeader('Content-Type', type)
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), ficheImages()],
  base: BASE
})
