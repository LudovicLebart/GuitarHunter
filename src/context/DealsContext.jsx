import React, { createContext, useContext } from 'react';
import { useDealsManager } from '../hooks/useDealsManager';
import { useAuth } from '../hooks/useAuth';
import { useBotConfigContext } from './BotConfigContext';

const DealsContext = createContext(null);

export const DealsProvider = ({ children }) => {
  const { user } = useAuth();
  const { setError } = useBotConfigContext();
  const dealsManagerData = useDealsManager(user, setError);

  return (
    <DealsContext.Provider value={dealsManagerData}>
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
