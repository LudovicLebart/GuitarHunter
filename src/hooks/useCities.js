import { useState, useEffect, useCallback } from 'react';
import { onCitiesUpdate, addCity, deleteCity, toggleCityScannable } from '../services/firestoreService';

export const useCities = (user, setError) => {
  const [cities, setCities] = useState([]);
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

  useEffect(() => {
    if (!user) return;

    const unsubscribe = onCitiesUpdate(
      (data) => setCities(data),
      (err) => setError(err.message)
    );

    return () => unsubscribe();
  }, [user, setError]);

  const handleAddCity = useCallback(async () => {
    if (!newCityName || !newCityId) return;
    try {
      await addCity(newCityName, newCityId);
      setNewCityName('');
      setNewCityId('');
    } catch (e) {
      setError(e.message);
    }
  }, [newCityName, newCityId, setError]);

  const handleDeleteCity = useCallback(async (id) => {
    if (window.confirm('Voulez-vous vraiment supprimer cette ville ?')) {
      try {
        await deleteCity(id);
      } catch (e) {
        setError(e.message);
      }
    }
  }, [setError]);

  const handleToggleScannable = useCallback(async (id, currentStatus) => {
      try {
          await toggleCityScannable(id, currentStatus);
      } catch (e) {
          setError(e.message);
      }
  }, [setError]);

  return {
    cities,
    newCityName, setNewCityName,
    newCityId, setNewCityId,
    handleAddCity,
    handleDeleteCity,
    handleToggleScannable
  };
};
