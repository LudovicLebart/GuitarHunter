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

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Vérification de la session...' });
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        setAuthStatus({ status: 'success', msg: `Connecté (${firebaseUser.email})` });

        // Vérification défensive côté client (custom claim) — la vraie protection est côté API
        // (`get_admin_uid`, routes `/admin/*`).
        try {
          const tokenResult = await firebaseUser.getIdTokenResult();
          setIsAdmin(tokenResult.claims?.admin === true);
        } catch (e) {
          console.error("Erreur lecture du token (claims admin):", e);
          setIsAdmin(false);
        }

        // S'assurer que la ligne utilisateur existe en base (idempotent) : le bot découvre les
        // utilisateurs en lisant Postgres, un nouvel inscrit sans ligne n'aurait jamais de bot.
        try {
          await ensureUser();
        } catch (e) {
          console.error("Erreur initialisation de l'utilisateur:", e);
          // Signaler à l'UI : connecté à Firebase Auth mais absent de la base → pas de bot.
          setAuthStatus({
            status: 'warning',
            msg: `Connecté (${firebaseUser.email}) — ⚠️ Utilisateur non initialisé côté serveur : ${e.message}`
          });
        }
      } else {
        setAuthStatus({ status: 'unauthenticated', msg: 'Non connecté' });
        setIsAdmin(false);
      }
    });
    return () => unsubscribe();
  }, []);

  const signIn = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Connexion en cours...' });
    try {
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      await ensureUser();
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signUp = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Création du compte...' });
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      await ensureUser();
      setAuthStatus({ status: 'success', msg: 'Compte créé et initialisé' });
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
    await firebaseSignOut(auth);
    setAuthStatus({ status: 'unauthenticated', msg: 'Déconnecté' });
  };

  return { user, authStatus, isAdmin, signIn, signUp, resetPassword, signOut };
};
