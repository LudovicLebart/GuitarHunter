import { useState, useEffect, useCallback } from 'react';
import { collection, onSnapshot, addDoc, deleteDoc, doc } from 'firebase/firestore';
import { db } from '../services/firebase';

const PYTHON_USER_ID = "00737242777130596039";
const APP_ID = "c_5d118e719dbddbfc_index.html-217";

export const useCities = (user, setError) => {
  const [cities, setCities] = useState([]);
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

  useEffect(() => {
    if (!user) return;
    const citiesRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'cities');
    const unsubscribe = onSnapshot(citiesRef, (snapshot) => {
      const citiesData = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
      setCities(citiesData);
    });
    return () => unsubscribe();
  }, [user]);

  const handleAddCity = useCallback(async () => {
    if (!newCityName || !newCityId) return;
    try {
      const citiesRef = collection(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'cities');
      await addDoc(citiesRef, {
        name: newCityName,
        id: newCityId,
        createdAt: new Date()
      });
      setNewCityName('');
      setNewCityId('');
    } catch (e) {
      setError("Erreur ajout ville: " + e.message);
    }
  }, [newCityName, newCityId, setError]);

  const handleDeleteCity = useCallback(async (docId) => {
    try {
      await deleteDoc(doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID, 'cities', docId));
    } catch (e) {
      setError("Erreur suppression ville");
    }
  }, [setError]);

  return {
    cities,
    newCityName, setNewCityName,
    newCityId, setNewCityId,
    handleAddCity,
    handleDeleteCity
  };
};
