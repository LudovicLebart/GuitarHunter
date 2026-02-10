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

// Helper ROBUSTE : Assure qu'on a une liste plate de chaînes, sans sauts de ligne internes
const ensureArray = (val) => {
  if (val === null || val === undefined) return [];
  
  // 1. Aplatir les tableaux imbriqués éventuels (gestion des cas limites)
  const flatVal = Array.isArray(val) ? val.flat(Infinity) : [val];
  
  // 2. Traiter chaque élément pour découper les sauts de ligne
  return flatVal
    .flatMap(item => {
        if (item === null || item === undefined) return [];
        const str = String(item);
        // Découpage robuste : 
        // - Sauts de ligne échappés (\\n)
        // - Sauts de ligne Windows (\r\n)
        // - Sauts de ligne Mac/Linux (\r ou \n)
        return str.split(/\\n|\r\n|\r|\n/);
    })
    .map(item => item.trim())
    .filter(item => item !== ""); 
};

const DEFAULT_PROMPT = ensureArray(promptsData.persona || promptsData.system_prompt);
const DEFAULT_VERDICT_RULES = ensureArray(promptsData.verdict_rules);
const DEFAULT_REASONING_INSTRUCTION = ensureArray(promptsData.reasoning_instruction);
const DEFAULT_USER_PROMPT = ensureArray(promptsData.user_prompt);
// Valeur par défaut temporaire pour le frontend, le vrai défaut est dans config.py
const DEFAULT_EXCLUSION_KEYWORDS = [
    "First Act", "Esteban", "Rogue", "Silvertone", "Spectrum", 
    "Denver", "Groove", "Stagg", "Maestro by Gibson", "Beaver Creek", "kmise"
];

export const useBotConfig = (user) => {
  const [configStatus, setConfigStatus] = useState({ status: 'pending', msg: 'En attente' });
  const [error, setError] = useState(null);
  
  // States for configuration values
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [verdictRules, setVerdictRules] = useState(DEFAULT_VERDICT_RULES);
  const [reasoningInstruction, setReasoningInstruction] = useState(DEFAULT_REASONING_INSTRUCTION);
  const [userPrompt, setUserPrompt] = useState(DEFAULT_USER_PROMPT);
  const [exclusionKeywords, setExclusionKeywords] = useState(DEFAULT_EXCLUSION_KEYWORDS); // Nouvel état
  
  const [scanConfig, setScanConfig] = useState({
      max_ads: 5, frequency: 60, location: 'montreal', distance: 60, min_price: 0, max_price: 150, search_query: "electric guitar"
  });
  const [geminiModel, setGeminiModel] = useState('gemini-2.0-flash');

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
      
      // On applique le ensureArray renforcé sur toutes les données entrantes
      if (data.prompt) setPrompt(ensureArray(data.prompt));
      if (data.verdictRules) setVerdictRules(ensureArray(data.verdictRules));
      if (data.reasoningInstruction) setReasoningInstruction(ensureArray(data.reasoningInstruction));
      if (data.userPrompt) setUserPrompt(ensureArray(data.userPrompt));
      if (data.exclusionKeywords) setExclusionKeywords(ensureArray(data.exclusionKeywords)); // Mise à jour depuis Firestore
      
      if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));
      if (data.geminiModel) setGeminiModel(data.geminiModel);
      
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
        prompt: ensureArray(promptsData.persona || promptsData.system_prompt),
        verdictRules: ensureArray(promptsData.verdict_rules),
        reasoningInstruction: ensureArray(promptsData.reasoning_instruction),
        userPrompt: ensureArray(promptsData.user_prompt),
        exclusionKeywords: DEFAULT_EXCLUSION_KEYWORDS, // Reset de la blacklist
        geminiModel: 'gemini-2.0-flash'
      };
      
      setPrompt(defaults.prompt);
      setVerdictRules(defaults.verdictRules);
      setReasoningInstruction(defaults.reasoningInstruction);
      setUserPrompt(defaults.userPrompt);
      setExclusionKeywords(defaults.exclusionKeywords);
      setGeminiModel(defaults.geminiModel);

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
    exclusionKeywords, setExclusionKeywords, // Export des nouveaux états
    scanConfig, setScanConfig,
    geminiModel, setGeminiModel,
    isRefreshing, isCleaning, isReanalyzingAll, isScanningUrl,
    saveConfig,
    handleManualRefresh, handleManualCleanup,
    handleRelaunchAll, handleScanSpecificUrl,
    handleResetDefaults
  };
};
