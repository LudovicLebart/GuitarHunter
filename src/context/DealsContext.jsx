import React, { createContext, useContext } from 'react';
import { useDeals } from '../hooks/useDeals';
import { useAuth } from '../hooks/useAuth';
import { useBotConfigContext } from './BotConfigContext';

const DealsContext = createContext(null);

export const DealsProvider = ({ children }) => {
  const { user } = useAuth();
  const { setError } = useBotConfigContext(); // On récupère setError du contexte de config
  const dealsData = useDeals(user, setError);

  return (
    <DealsContext.Provider value={dealsData}>
      {children}
    </DealsContext.Provider>
  );
};

export const useDealsContext = () => {
  const context = useContext(DealsContext);
  if (!context) {
    throw new Error('useDealsContext must be used within a DealsProvider');
  }
  return context;
};
