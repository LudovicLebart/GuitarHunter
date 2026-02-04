import { useState, useEffect, useCallback } from 'react';
import { onCitiesUpdate, addCity, deleteCity } from '../services/firestoreService';

export const useCities = (user, setError) => {
  const [cities, setCities] = useState([]);
  const [newCityName, setNewCityName] = useState('');
  const [newCityId, setNewCityId] = useState('');

  useEffect(() => {
    if (!user) return;

    const handleUpdate = (citiesData) => {
      setCities(citiesData);
    };

    const handleError = (err) => {
      setError(err.message);
    };

    const unsubscribe = onCitiesUpdate(handleUpdate, handleError);
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

  const handleDeleteCity = useCallback(async (cityId) => {
    try {
      await deleteCity(cityId);
    } catch (e) {
      setError(e.message);
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
