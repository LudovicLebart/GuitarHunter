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
  const flatVal = Array.isArray(val) ? val.flat(Infinity) : [val];
  return flatVal
    .flatMap(item => {
      if (item === null || item === undefined) return [];
      const str = String(item);
      return str.split(/\\n|\r\n|\r|\n/);
    })
    .map(item => item.trim())
    .filter(item => item !== "");
};

const DEFAULT_MAIN_PROMPT = ensureArray(promptsData.main_analysis_prompt);
const DEFAULT_GATEKEEPER_INSTRUCTION = ensureArray(promptsData.gatekeeper_verbosity_instruction);
const DEFAULT_EXPERT_CONTEXT = ensureArray(promptsData.expert_context_instruction);
const DEFAULT_EXCLUSION_KEYWORDS = [
  "First Act", "Esteban", "Rogue", "Silvertone", "Spectrum",
  "Denver", "Groove", "Stagg", "Maestro by Gibson", "Beaver Creek", "kmise"
];

export const useBotConfig = (user) => {
  const [configStatus, setConfigStatus] = useState({ status: 'pending', msg: 'En attente' });
  const [error, setError] = useState(null);

  // --- NOUVELLE GESTION DE LA CONFIGURATION ---
  const [scanConfig, setScanConfig] = useState({
    max_ads: 5, frequency: 60, location: 'montreal', distance: 60, min_price: 0, max_price: 150, search_query: "electric guitar"
  });
  const [exclusionKeywords, setExclusionKeywords] = useState(DEFAULT_EXCLUSION_KEYWORDS);

  // Mise à jour des modèles par défaut pour correspondre au backend
  const [analysisConfig, setAnalysisConfig] = useState({
    gatekeeperModel: 'gemini-2.5-flash-lite',
    expertModel: 'gemini-2.5-flash',
    mainAnalysisPrompt: DEFAULT_MAIN_PROMPT,
    gatekeeperVerbosityInstruction: DEFAULT_GATEKEEPER_INSTRUCTION,
    expertContextInstruction: DEFAULT_EXPERT_CONTEXT
  });

  // Nouvel état pour stocker la liste des modèles disponibles reçue du backend
  const [availableModels, setAvailableModels] = useState([]);

  // Nouvel état pour la limite de logs
  const [logLimit, setLogLimit] = useState(100);

  // UI feedback states derived from botStatus
  const [botStatus, setBotStatus] = useState('idle');
  const isRefreshing = botStatus === 'scanning';
  const isCleaning = botStatus === 'cleaning';
  const isReanalyzingAll = botStatus === 'reanalyzing_all';
  const isScanningUrl = botStatus === 'scanning_url';

  useEffect(() => {
    if (!user) return;

    const handleUpdate = (data) => {
      console.log("🔄 useBotConfig: Received update from Firestore", data);
      setConfigStatus({ status: 'success', msg: 'Dossier Python trouvé' });

      if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));
      if (data.exclusionKeywords) setExclusionKeywords(ensureArray(data.exclusionKeywords));

      // Récupération des modèles disponibles
      if (data.availableModels && Array.isArray(data.availableModels)) {
        setAvailableModels(data.availableModels);
      }

      // Fusionne la config d'analyse pour ne pas écraser les champs non gérés par l'UI
      if (data.analysisConfig) {
        console.log("📝 Updating analysisConfig from Firestore data");
        setAnalysisConfig(prev => ({
          ...prev,
          ...data.analysisConfig,
          mainAnalysisPrompt: ensureArray(data.analysisConfig.mainAnalysisPrompt || prev.mainAnalysisPrompt),
          gatekeeperVerbosityInstruction: ensureArray(data.analysisConfig.gatekeeperVerbosityInstruction || prev.gatekeeperVerbosityInstruction),
          expertContextInstruction: ensureArray(data.analysisConfig.expertContextInstruction || prev.expertContextInstruction),
        }));
      }

      if (data.logLimit) {
        setLogLimit(data.logLimit);
      }

      if (data.botStatus) setBotStatus(data.botStatus);

      if (data.scanError) {
        setError(data.scanError);
      } else if (error && error.startsWith("Ville")) {
        setError(null);
      }
    };

    const handleError = (e) => {
      console.error("❌ useBotConfig: Error receiving update", e);
      setConfigStatus({ status: 'error', msg: e.message });
    };

    const unsubscribe = onBotConfigUpdate(handleUpdate, handleError);

    return () => unsubscribe();
  }, [user, error]);

  const saveConfig = useCallback(async (newVal) => {
    try {
      console.log("💾 Saving config...", newVal);
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
      const defaultAnalysis = {
        gatekeeperModel: 'gemini-2.5-flash-lite',
        expertModel: 'gemini-2.5-flash',
        mainAnalysisPrompt: DEFAULT_MAIN_PROMPT,
        gatekeeperVerbosityInstruction: DEFAULT_GATEKEEPER_INSTRUCTION,
        expertContextInstruction: DEFAULT_EXPERT_CONTEXT
      };

      setExclusionKeywords(DEFAULT_EXCLUSION_KEYWORDS);
      setAnalysisConfig(defaultAnalysis);
      setLogLimit(100);

      try {
        await updateUserConfig({
          exclusionKeywords: DEFAULT_EXCLUSION_KEYWORDS,
          'analysisConfig.gatekeeperModel': defaultAnalysis.gatekeeperModel,
          'analysisConfig.expertModel': defaultAnalysis.expertModel,
          'analysisConfig.mainAnalysisPrompt': defaultAnalysis.mainAnalysisPrompt,
          'analysisConfig.gatekeeperVerbosityInstruction': defaultAnalysis.gatekeeperVerbosityInstruction,
          'analysisConfig.expertContextInstruction': defaultAnalysis.expertContextInstruction,
          logLimit: 100
        });
      } catch (e) {
        console.error("Erreur lors du reset:", e);
        setError(e.message);
      }
    }
  }, []);

  return {
    configStatus, error, setError,
    scanConfig, setScanConfig,
    exclusionKeywords, setExclusionKeywords,
    analysisConfig, setAnalysisConfig,
    availableModels, // On expose la liste des modèles
    logLimit, setLogLimit, // On expose la limite de logs
    isRefreshing, isCleaning, isReanalyzingAll, isScanningUrl,
    saveConfig,
    handleManualRefresh, handleManualCleanup,
    handleRelaunchAll, handleScanSpecificUrl,
    handleResetDefaults
  };
};
