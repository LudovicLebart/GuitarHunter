import { useState, useEffect, useCallback } from 'react';
import { onCitiesUpdate, requestAddCity, deleteCity, toggleCityScannable, onCommandUpdate } from '../services/firestoreService';

export const useCities = (user, setError) => {
  const [cities, setCities] = useState([]);
  const [newCityName, setNewCityName] = useState('');
  const [isAddingCity, setIsAddingCity] = useState(false);

  useEffect(() => {
    if (!user) return;

    const unsubscribe = onCitiesUpdate(
      (data) => setCities(data),
      (err) => setError(err.message)
    );

    return () => unsubscribe();
  }, [user, setError]);

  const handleAddCity = useCallback(async () => {
    if (!newCityName) return;
    setIsAddingCity(true);
    try {
      const commandDocRef = await requestAddCity(newCityName);
      
      // Écouter le résultat de la commande
      const unsubscribe = onCommandUpdate(commandDocRef.id, (data) => {
          if (data.status === 'completed') {
              setNewCityName('');
              setIsAddingCity(false);
              unsubscribe(); // Arrêter d'écouter
          } else if (data.status === 'failed') {
              setError(data.error || "Erreur lors de l'ajout de la ville.");
              setIsAddingCity(false);
              unsubscribe(); // Arrêter d'écouter
          }
      });

    } catch (e) {
      setError(e.message);
      setIsAddingCity(false);
    }
  }, [newCityName, setError]);

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
    isAddingCity,
    handleAddCity,
    handleDeleteCity,
    handleToggleScannable
  };
};
