import { clearIndexCache } from '../utils/indexCache';
import { useState, useEffect } from 'react';
import { 
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
  signOut as firebaseSignOut,
  onAuthStateChanged
} from 'firebase/auth';
import { auth } from '../services/firebase';
import { ensureUser } from '../services/apiService';

// Attente maximale de l'initialisation de la ligne utilisateur avant d'ouvrir l'application (au-delà, l'application s'ouvre
// avec un avertissement : un compte tout neuf peut alors recevoir des 404 jusqu'au prochain rechargement).
const ENSURE_USER_WAIT_MS = 10000;

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Vérification de la session...' });
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let seq = 0;
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      const mine = ++seq; // une connexion plus récente rend les suites de celle-ci caduques
      if (firebaseUser) {

        // Vérification défensive côté client (custom claim) — la vraie protection est côté API
        // (`get_admin_uid`, routes `/admin/*`).
        let admin = false;
        try {
          const tokenResult = await firebaseUser.getIdTokenResult();
          admin = tokenResult.claims?.admin === true;
        } catch (e) {
          console.error("Erreur lecture du token (claims admin):", e);
        }

        // S'assurer que la ligne utilisateur existe en base (idempotent) AVANT de publier `user` : les hooks de l'app
        // appellent l'API dès qu'ils voient l'utilisateur, et un nouvel inscrit sans ligne recevrait un 404. Seul
        // appel d'`ensureUser` : signIn/signUp passent par cet observateur.
        // L'attente est bornée : une API lente ne doit pas bloquer l'accès à l'application (avertissement affiché ensuite).
        let initError = null;
        let settled = false;
        const init = ensureUser().then(() => {}, (e) => {
          console.error("Erreur initialisation de l'utilisateur:", e);
          initError = e;
        }).finally(() => { settled = true; });
        let waitTimer;
        await Promise.race([init, new Promise((resolve) => { waitTimer = setTimeout(resolve, ENSURE_USER_WAIT_MS); })]);
        clearTimeout(waitTimer);
        if (mine !== seq) return;
        // Signaler à l'UI : connecté à Firebase Auth mais absent de la base → pas de bot.
        const warn = () => ({ status: 'warning', msg: `Connecté (${firebaseUser.email}) — ⚠️ Utilisateur non initialisé côté serveur : ${initError.message}` });
        setIsAdmin(admin);
        setUser(firebaseUser);
        setAuthStatus(initError ? warn() : { status: 'success', msg: `Connecté (${firebaseUser.email})` });
        if (!settled) init.then(() => { if (mine === seq && initError) setAuthStatus(warn()); });
      } else {
        setUser(null);
        setAuthStatus({ status: 'unauthenticated', msg: 'Non connecté' });
        setIsAdmin(false);
      }
    });
    return () => unsubscribe();
  }, []);

  const signIn = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Connexion en cours...' });
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signUp = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Création du compte...' });
    try {
      await createUserWithEmailAndPassword(auth, email, password); // l'observateur initialise la ligne en base
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const resetPassword = async (email) => {
    setAuthStatus({ status: 'loading', msg: 'Envoi de l\'email de réinitialisation...' });
    try {
      await sendPasswordResetEmail(auth, email);
      setAuthStatus({ status: 'unauthenticated', msg: 'Email envoyé' });
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signOut = async () => {
    await clearIndexCache(); // le cache de l'index ne doit pas survivre à la déconnexion (appareil partagé)
    await firebaseSignOut(auth);
    setAuthStatus({ status: 'unauthenticated', msg: 'Déconnecté' });
  };

  return { user, authStatus, isAdmin, signIn, signUp, resetPassword, signOut };
};
