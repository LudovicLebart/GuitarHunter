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

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Vérification de la session...' });

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        setAuthStatus({ status: 'success', msg: `Connecté (${firebaseUser.email})` });
        
        // S'assurer que le document utilisateur existe pour le backend (cas de persistance session)
        try {
          const userDocRef = doc(db, 'artifacts', APP_ID, 'users', firebaseUser.uid);
          const snap = await getDoc(userDocRef);
          
          if (!snap.exists()) {
            await setDoc(userDocRef, {
              email: firebaseUser.email,
              createdAt: serverTimestamp(),
              botStatus: 'idle'
            });
          } else {
            await updateDoc(userDocRef, { 
              lastSeen: serverTimestamp() 
            });
          }
        } catch (e) {
          console.error("Erreur initialisation document utilisateur:", e);
        }
      } else {
        setAuthStatus({ status: 'unauthenticated', msg: 'Non connecté' });
      }
    });
    return () => unsubscribe();
  }, []);

  const signIn = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Connexion en cours...' });
    try {
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      const connectedUser = userCredential.user;

      // Initialisation/Mise à jour du document utilisateur
      const userDocRef = doc(db, 'artifacts', APP_ID, 'users', connectedUser.uid);
      const snap = await getDoc(userDocRef);
      if (!snap.exists()) {
        await setDoc(userDocRef, {
          email: connectedUser.email,
          createdAt: serverTimestamp(),
          botStatus: 'idle'
        });
      } else {
        await updateDoc(userDocRef, { lastLogin: serverTimestamp() });
      }

    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signUp = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Création du compte...' });
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      const newUser = userCredential.user;

      // Initialisation du document utilisateur pour que le backend le découvre
      const userDocRef = doc(db, 'artifacts', APP_ID, 'users', newUser.uid);
      await setDoc(userDocRef, {
        email: newUser.email,
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

  return { user, authStatus, signIn, signUp, resetPassword, signOut };
};
