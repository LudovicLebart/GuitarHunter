import { useState, useEffect } from 'react';
import { signInAnonymously, onAuthStateChanged } from 'firebase/auth';
import { auth } from '../services/firebase';

export const useAuth = () => {
  const [user, setUser] = useState(null);
  const [authStatus, setAuthStatus] = useState({ status: 'loading', msg: 'Connexion...' });

  useEffect(() => {
    const initAuth = async () => {
      try {
        await signInAnonymously(auth);
        setAuthStatus({ status: 'success', msg: 'Authentifié' });
      } catch (err) {
        setAuthStatus({ status: 'error', msg: err.message });
      }
    };
    initAuth();
    const unsubscribe = onAuthStateChanged(auth, setUser);
    return () => unsubscribe();
  }, []);

  return { user, authStatus };
};
