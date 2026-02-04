import React, { createContext, useContext } from 'react';
import { useBotConfig } from '../hooks/useBotConfig';
import { useAuth } from '../hooks/useAuth';

const BotConfigContext = createContext(null);

export const BotConfigProvider = ({ children }) => {
  const { user } = useAuth();
  const botConfig = useBotConfig(user);

  return (
    <BotConfigContext.Provider value={botConfig}>
      {children}
    </BotConfigContext.Provider>
  );
};

export const useBotConfigContext = () => {
  const context = useContext(BotConfigContext);
  if (!context) {
    throw new Error('useBotConfigContext must be used within a BotConfigProvider');
  }
  return context;
};
