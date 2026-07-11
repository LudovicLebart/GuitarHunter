import { useState, useEffect } from 'react';
import { 
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
  signOut as firebaseSignOut,
  onAuthStateChanged
} from 'firebase/auth';
import { doc, setDoc, getDoc, updateDoc, serverTimestamp } from 'firebase/firestore';
import { auth, db } from '../services/firebase';

const APP_ID = import.meta.env.VITE_APP_ID_TARGET;

/**
 * Assure que le document utilisateur existe dans Firestore.
 * Crée le document s'il n'existe pas, sinon met à jour `updateField`.
 * @param {string} uid - UID Firebase Auth
 * @param {string} email - email de l'utilisateur
 * @param {string} updateField - champ à mettre à jour si le doc existe ('lastSeen' | 'lastLogin')
 */
const ensureUserDoc = async (uid, email, updateField = 'lastSeen') => {
  const userDocRef = doc(db, 'artifacts', APP_ID, 'users', uid);
  const snap = await getDoc(userDocRef);
  if (!snap.exists()) {
    await setDoc(userDocRef, {
      email,
      createdAt: serverTimestamp(),
      botStatus: 'idle'
    });
  } else {
    await updateDoc(userDocRef, { [updateField]: serverTimestamp() });
  }
};

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Vérification de la session...' });
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        setAuthStatus({ status: 'success', msg: `Connecté (${firebaseUser.email})` });

        // Vérification défensive côté client (custom claim) — la vraie protection
        // reste les règles Firestore (isAdmin() dans firestore.rules).
        try {
          const tokenResult = await firebaseUser.getIdTokenResult();
          setIsAdmin(tokenResult.claims?.admin === true);
        } catch (e) {
          console.error("Erreur lecture du token (claims admin):", e);
          setIsAdmin(false);
        }

        // S'assurer que le document utilisateur existe pour le backend (cas de persistance session)
        try {
          await ensureUserDoc(firebaseUser.uid, firebaseUser.email, 'lastSeen');
        } catch (e) {
          console.error("Erreur initialisation document utilisateur:", e);
          // Signaler à l'UI : l'utilisateur est connecté Firebase Auth mais le document
          // Firestore est inaccessible → le backend ne pourra pas découvrir cet utilisateur.
          setAuthStatus({
            status: 'warning',
            msg: `Connecté (${firebaseUser.email}) — ⚠️ Document utilisateur inaccessible : ${e.message}`
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
      await ensureUserDoc(userCredential.user.uid, userCredential.user.email, 'lastLogin');
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signUp = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Création du compte...' });
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      // setDoc avec merge:true pour le signup (document garanti inexistant, mais sécurité idémpotente)
      const userDocRef = doc(db, 'artifacts', APP_ID, 'users', userCredential.user.uid);
      await setDoc(userDocRef, {
        email: userCredential.user.email,
        createdAt: serverTimestamp(),
        botStatus: 'idle'
      }, { merge: true });
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
