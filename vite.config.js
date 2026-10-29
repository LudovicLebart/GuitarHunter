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
      // Une image citée par une fiche mais absente de docs/fiches/img serait un 404 en production sans que rien ne casse :
      // on le dit bruyamment (sans bloquer le déploiement du site pour autant).
      const missing = missingFicheImages()
      if (missing.length) console.warn(`\n⚠️  Images de fiches introuvables dans docs/fiches/ (404 en production) :\n${missing.map((m) => `   - ${m}`).join('\n')}\n`)
    },
    configureServer(server) {
      server.middlewares.use(`${BASE}fiches/img`, (req, res, next) => {
        let file
        try { file = path.join(FICHE_IMAGES, decodeURIComponent((req.url || '/').split('?')[0])) } catch { return next() }   // %-encodage invalide : pas une image
        const type = IMAGE_TYPES[path.extname(file).toLowerCase()]
        // jamais en dehors du dossier des images, jamais autre chose qu'une image
        if (!type || !file.startsWith(FICHE_IMAGES + path.sep) || !fs.existsSync(file)) return next()
        res.setHeader('Content-Type', type)
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

// Images relatives (`![légende](img/<slug>/01-x.jpg)`) citées par les fiches mais absentes du dossier des images.
const missingFicheImages = () => {
  const dir = fileURLToPath(new URL('./docs/fiches', import.meta.url))
  const missing = []
  for (const name of fs.readdirSync(dir).filter((f) => f.endsWith('.md') && !f.startsWith('_') && f !== 'README.md')) {
    const text = fs.readFileSync(path.join(dir, name), 'utf8')
    for (const m of text.matchAll(/!\[[^\]]*\]\(((?!https?:|\/)[^)\s]+)\)/g)) {
      if (!fs.existsSync(path.join(dir, m[1]))) missing.push(`${name} : ${m[1]}`)
    }
  }
  return missing
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), ficheImages()],
  base: BASE
})
