import { useState, useEffect, useCallback } from 'react';
import {
  onBotConfigUpdate,
  updateUserConfig,
  triggerManualRefresh,
  triggerManualCleanup,
  triggerRelaunchAll,
  triggerScanSpecificUrl,
  resetBotConfigToDefaults
} from '../services/firestoreService';
import promptsData from '../../prompts.json';

const DEFAULT_PROMPT = promptsData.system_prompt;
const DEFAULT_VERDICT_RULES = promptsData.verdict_rules;
const DEFAULT_REASONING_INSTRUCTION = promptsData.reasoning_instruction;
const DEFAULT_USER_PROMPT = promptsData.user_prompt;

export const useBotConfig = (user) => {
  const [configStatus, setConfigStatus] = useState({ status: 'pending', msg: 'En attente' });
  const [error, setError] = useState(null);
  
  // States for configuration values
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [verdictRules, setVerdictRules] = useState(DEFAULT_VERDICT_RULES);
  const [reasoningInstruction, setReasoningInstruction] = useState(DEFAULT_REASONING_INSTRUCTION);
  const [userPrompt, setUserPrompt] = useState(DEFAULT_USER_PROMPT);
  const [scanConfig, setScanConfig] = useState({
      max_ads: 5, frequency: 60, location: 'montreal', distance: 60, min_price: 0, max_price: 150, search_query: "electric guitar"
  });

  // UI feedback states derived from botStatus
  const [botStatus, setBotStatus] = useState('idle');
  const isRefreshing = botStatus === 'scanning';
  const isCleaning = botStatus === 'cleaning';
  const isReanalyzingAll = botStatus === 'reanalyzing_all';
  const isScanningUrl = botStatus === 'scanning_url';

  useEffect(() => {
    if (!user) return;

    const handleUpdate = (data) => {
      setConfigStatus({ status: 'success', msg: 'Dossier Python trouvé' });
      
      if (data.prompt) setPrompt(data.prompt);
      if (data.verdictRules) setVerdictRules(data.verdictRules);
      if (data.reasoningInstruction) setReasoningInstruction(data.reasoningInstruction);
      if (data.userPrompt) setUserPrompt(data.userPrompt);
      if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));
      
      // Update bot status from Firestore
      if (data.botStatus) setBotStatus(data.botStatus);

      if (data.scanError) {
        setError(data.scanError);
      } else if (error && error.startsWith("Ville")) {
         setError(null);
      }
    };

    const handleError = (e) => {
      setConfigStatus({ status: 'error', msg: e.message });
    };

    const unsubscribe = onBotConfigUpdate(handleUpdate, handleError);

    return () => unsubscribe();
  }, [user, error]);

  const saveConfig = useCallback(async (newVal) => {
    try {
      await updateUserConfig(newVal);
    } catch (e) { 
      setError(e.message); 
    }
  }, []);

  const handleManualRefresh = useCallback(async () => {
    try {
      await triggerManualRefresh();
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleManualCleanup = useCallback(async () => {
    try {
      await triggerManualCleanup();
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleRelaunchAll = useCallback(async () => {
    if (window.confirm("⚠️ ATTENTION : Voulez-vous vraiment relancer l'analyse IA pour TOUTES les annonces ?")) {
        try {
            await triggerRelaunchAll();
        } catch (e) {
            setError(e.message);
        }
    }
  }, []);

  const handleScanSpecificUrl = useCallback(async (specificUrl, setSpecificUrl) => {
    if (!specificUrl) return;
    try {
      await triggerScanSpecificUrl(specificUrl);
      setSpecificUrl('');
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const handleResetDefaults = useCallback(async () => {
    if (window.confirm("Voulez-vous vraiment réinitialiser les paramètres du bot aux valeurs par défaut ?")) {
      const defaults = {
        prompt: DEFAULT_PROMPT,
        verdictRules: DEFAULT_VERDICT_RULES,
        reasoningInstruction: DEFAULT_REASONING_INSTRUCTION,
        userPrompt: DEFAULT_USER_PROMPT
      };
      setPrompt(DEFAULT_PROMPT);
      setVerdictRules(DEFAULT_VERDICT_RULES);
      setReasoningInstruction(DEFAULT_REASONING_INSTRUCTION);
      setUserPrompt(DEFAULT_USER_PROMPT);
      try {
        await resetBotConfigToDefaults(defaults);
      } catch(e) {
        setError(e.message);
      }
    }
  }, []);

  return {
    configStatus, error, setError,
    prompt, setPrompt,
    verdictRules, setVerdictRules,
    reasoningInstruction, setReasoningInstruction,
    userPrompt, setUserPrompt,
    scanConfig, setScanConfig,
    isRefreshing, isCleaning, isReanalyzingAll, isScanningUrl,
    saveConfig,
    handleManualRefresh, handleManualCleanup,
    handleRelaunchAll, handleScanSpecificUrl,
    handleResetDefaults
  };
};
