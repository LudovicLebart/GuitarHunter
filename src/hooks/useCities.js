import { useState, useEffect, useCallback } from 'react';
import { onCitiesUpdate, requestAddCity, deleteCity, toggleCityScannable, setCityKijijiRadius, onCommandUpdate } from '../services/firestoreService';

export const useCities = (user, setError) => {
  const [cities, setCities] = useState([]);
  const [newCityName, setNewCityName] = useState('');
  const [isAddingCity, setIsAddingCity] = useState(false);

  useEffect(() => {
    if (!user) return;
    const uid = user.uid;
    const unsubscribe = onCitiesUpdate(
      (data) => setCities(data),
      (err) => setError(err.message),
      uid
    );

    return () => unsubscribe();
  }, [user, setError]);

  const handleAddCity = useCallback(async (cityInput) => {
    // `cityInput` : chaîne simple (repli historique) ou objet structuré
    // `{name, latitude, longitude, regionHint}` venant d'une suggestion Photon choisie
    // explicitement par l'utilisateur (voir ConfigPanel.jsx/useCitySuggestions.js) — traduit ici
    // en `region_hint` pour matcher le payload attendu par `bot.py::add_city_auto()`.
    const isStructured = cityInput && typeof cityInput === 'object';
    const targetName = (isStructured ? cityInput.name : (typeof cityInput === 'string' ? cityInput : newCityName)).trim();
    if (!targetName || !user) return;
    const uid = user.uid;
    setIsAddingCity(true);
    try {
      const payload = isStructured
        ? { name: targetName, latitude: cityInput.latitude, longitude: cityInput.longitude, region_hint: cityInput.regionHint }
        : targetName;
      const commandDocRef = await requestAddCity(payload, uid);

      const unsubscribe = onCommandUpdate(commandDocRef.id, (data) => {
          if (data.status === 'completed') {
              setNewCityName('');
              setIsAddingCity(false);
              unsubscribe();
          } else if (data.status === 'failed') {
              setError(data.error || "Erreur lors de l'ajout de la ville.");
              setIsAddingCity(false);
              setNewCityName('');
              unsubscribe();
          }
      }, uid);

    } catch (e) {
      setError(e.message);
      setIsAddingCity(false);
    }
  }, [newCityName, user, setError]);

  const handleDeleteCity = useCallback(async (id) => {
    if (!user) return;
    if (window.confirm('Voulez-vous vraiment supprimer cette ville ?')) {
      try {
        await deleteCity(id, user.uid);
      } catch (e) {
        setError(e.message);
      }
    }
  }, [user, setError]);

  const handleToggleScannable = useCallback(async (id, currentStatus) => {
      if (!user) return;
      try {
          await toggleCityScannable(id, currentStatus, user.uid);
      } catch (e) {
          setError(e.message);
      }
  }, [user, setError]);

  const handleSetCityKijijiRadius = useCallback(async (id, radiusKm) => {
      if (!user) return;
      try {
          await setCityKijijiRadius(id, radiusKm, user.uid);
      } catch (e) {
          setError(e.message);
      }
  }, [user, setError]);

  return {
    cities,
    newCityName, setNewCityName,
    isAddingCity,
    handleAddCity,
    handleDeleteCity,
    handleToggleScannable,
    handleSetCityKijijiRadius
  };
};
