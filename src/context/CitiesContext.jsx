import React, { createContext, useContext } from 'react';
import { useCities } from '../hooks/useCities';
import { useAuth } from '../hooks/useAuth';
import { useBotConfigContext } from './BotConfigContext';

const CitiesContext = createContext(null);

export const CitiesProvider = ({ children }) => {
  const { user } = useAuth();
  const { setError } = useBotConfigContext();
  const citiesData = useCities(user, setError);

  return (
    <CitiesContext.Provider value={citiesData}>
      {children}
    </CitiesContext.Provider>
  );
};

export const useCitiesContext = () => {
  const context = useContext(CitiesContext);
  if (!context) {
    throw new Error('useCitiesContext must be used within a CitiesProvider');
  }
  return context;
};
