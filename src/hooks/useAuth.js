import { useState, useEffect } from 'react';
import {
  signInWithEmailAndPassword,
  signOut as firebaseSignOut,
  onAuthStateChanged
} from 'firebase/auth';
import { auth } from '../services/firebase';

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Vérification de la session...' });

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      if (firebaseUser) {
        setAuthStatus({ status: 'success', msg: `Connecté (${firebaseUser.email})` });
      } else {
        setAuthStatus({ status: 'unauthenticated', msg: 'Non connecté' });
      }
    });
    return () => unsubscribe();
  }, []);

  const signIn = async (email, password) => {
    setAuthStatus({ status: 'loading', msg: 'Connexion en cours...' });
    try {
      await signInWithEmailAndPassword(auth, email, password);
      // onAuthStateChanged mettra à jour user et authStatus automatiquement
    } catch (err) {
      setAuthStatus({ status: 'error', msg: err.message });
      throw err;
    }
  };

  const signOut = async () => {
    await firebaseSignOut(auth);
    setAuthStatus({ status: 'unauthenticated', msg: 'Déconnecté' });
  };

  return { user, authStatus, signIn, signOut };
};
