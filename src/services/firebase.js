import { initializeApp } from 'firebase/app';
import { getFirestore } from 'firebase/firestore';
import { getAuth } from 'firebase/auth';
import { getStorage } from 'firebase/storage';
import { initializeAppCheck, ReCaptchaEnterpriseProvider } from 'firebase/app-check';
import { getAI, GoogleAIBackend } from 'firebase/ai';

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID
};

console.log("🔥 Config Firebase:", { ...firebaseConfig, apiKey: firebaseConfig.apiKey ? '***' : 'MISSING' });

let app, auth, db, ai, storage;
try {
  app = initializeApp(firebaseConfig);
  auth = getAuth(app);
  db = getFirestore(app);
  storage = getStorage(app);

  // App Check (2026-07-31) : protège le quota Gemini de Firebase AI Logic contre les appels non
  // autorisés. Nécessite une clé reCAPTCHA Enterprise enregistrée dans la console Firebase (App
  // Check) — étape manuelle, non faisable depuis un environnement sans accès au compte Firebase.
  // Sans VITE_RECAPTCHA_SITE_KEY, on saute l'activation plutôt que de planter (dev/CI sans cette
  // clé encore configurée).
  const recaptchaSiteKey = import.meta.env.VITE_RECAPTCHA_SITE_KEY;
  if (recaptchaSiteKey) {
    // Mode debug (2026-07-31) : reCAPTCHA Enterprise valide un vrai domaine de production, pas
    // `localhost` — en dev (`npm run dev`, import.meta.env.DEV mis par Vite), on bascule App
    // Check sur un jeton de debug plutôt que de désactiver toute la protection. Au premier
    // lancement, le jeton généré s'affiche dans la console du navigateur ; il doit être enregistré
    // une fois dans la console Firebase (App Check > Apps > ⋮ > Manage debug tokens) pour que les
    // appels en local soient acceptés. Jamais actif en build de production (import.meta.env.DEV
    // est toujours `false` dans `npm run build`).
    if (import.meta.env.DEV) {
      self.FIREBASE_APPCHECK_DEBUG_TOKEN = true;
      console.warn("🔥 App Check en mode DEBUG (dev local) — le jeton à enregistrer dans la console Firebase va s'afficher ci-dessous.");
    }
    initializeAppCheck(app, {
      provider: new ReCaptchaEnterpriseProvider(recaptchaSiteKey),
      isTokenAutoRefreshEnabled: true,
    });
    console.log("🔥 Firebase App Check activé.");
  } else {
    console.warn("🔥 VITE_RECAPTCHA_SITE_KEY absent — App Check désactivé (voir docs/reference/ARCHITECTURE.md § Chat Gemini).");
  }

  // Firebase AI Logic (2026-07-31) : appel direct Gemini depuis le client, backend Developer API
  // (cohérent avec GEMINI_API_KEY côté backend Python — pas de migration Vertex AI pour l'instant).
  ai = getAI(app, { backend: new GoogleAIBackend() });

  console.log("🔥 Firebase initialisé avec succès !");
} catch (error) {
  console.error("🔥 ERREUR FATALE LORS DE L'INITIALISATION DE FIREBASE:", error);
}

export { auth, db, ai, storage };
