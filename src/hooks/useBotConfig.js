import { useState, useEffect, useCallback } from 'react';
import {
  onBotConfigUpdate,
  updateUserConfig,
  triggerManualRefresh,
  triggerManualCleanup,
  triggerRelaunchAll,
  triggerScanSpecificUrl,
  resetBotConfigToDefaults,
  migrateOldDataToNewUser
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
const DEFAULT_REJECTION_VERDICTS = ensureArray(promptsData.rejection_verdicts || ["BAD_DEAL", "REJECTED_ITEM", "REJECTED_SERVICE", "INCOMPLETE_DATA"]);
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
    mainModel: 'gemini-2.5-flash',
    expertModel: 'gemini-2.5-pro',
    mainAnalysisPrompt: DEFAULT_MAIN_PROMPT,
    gatekeeperVerbosityInstruction: DEFAULT_GATEKEEPER_INSTRUCTION,
    expertContextInstruction: DEFAULT_EXPERT_CONTEXT,
    rejectionVerdicts: DEFAULT_REJECTION_VERDICTS
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
  const isPaused = botStatus === 'paused';

  useEffect(() => {
    if (!user) return;
    const uid = user.uid;
    const email = user.email;

    const initConfig = async () => {
      try {
        const migrated = await migrateOldDataToNewUser(uid, email);
        if (migrated) {
          console.log("🔄 Données migrées avec succès vers le compte administrateur !");
        }
      } catch (err) {
        console.error("Erreur inattendue lors de la vérification de la migration", err);
      }
    };

    // Lance la migration asynchrone avant d'écouter les mises à jour
    initConfig();

    const handleUpdate = (data) => {
      console.log("🔄 useBotConfig: Received update from Firestore", data);
      setConfigStatus({ status: 'success', msg: 'Dossier Python trouvé' });

      if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));
      if (data.exclusionKeywords) setExclusionKeywords(ensureArray(data.exclusionKeywords));

      if (data.availableModels && Array.isArray(data.availableModels)) {
        setAvailableModels(data.availableModels);
      }

      if (data.analysisConfig) {
        setAnalysisConfig(prev => ({
          ...prev,
          ...data.analysisConfig,
          mainAnalysisPrompt: ensureArray(data.analysisConfig.mainAnalysisPrompt || prev.mainAnalysisPrompt),
          gatekeeperVerbosityInstruction: ensureArray(data.analysisConfig.gatekeeperVerbosityInstruction || prev.gatekeeperVerbosityInstruction),
          expertContextInstruction: ensureArray(data.analysisConfig.expertContextInstruction || prev.expertContextInstruction),
          rejectionVerdicts: ensureArray(data.analysisConfig.rejectionVerdicts || prev.rejectionVerdicts),
        }));
      }

      if (data.logLimit) setLogLimit(data.logLimit);
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

    const unsubscribe = onBotConfigUpdate(handleUpdate, handleError, uid);
    return () => unsubscribe();
  }, [user, error]);

  const saveConfig = useCallback(async (newVal) => {
    if (!user) return;
    try {
      await updateUserConfig(newVal, user.uid);
    } catch (e) {
      setError(e.message);
    }
  }, [user]);

  const handleManualRefresh = useCallback(async () => {
    if (!user) return;
    try { await triggerManualRefresh(user.uid); } catch (e) { setError(e.message); }
  }, [user]);

  const handleManualCleanup = useCallback(async () => {
    if (!user) return;
    try { await triggerManualCleanup(user.uid); } catch (e) { setError(e.message); }
  }, [user]);

  const handleRelaunchAll = useCallback(async () => {
    if (!user) return;
    if (window.confirm("⚠️ ATTENTION : Voulez-vous vraiment relancer l'analyse IA pour TOUTES les annonces ?")) {
      try { await triggerRelaunchAll(user.uid); } catch (e) { setError(e.message); }
    }
  }, [user]);

  const handleScanSpecificUrl = useCallback(async (specificUrl, setSpecificUrl) => {
    if (!specificUrl || !user) return;
    try {
      await triggerScanSpecificUrl(specificUrl, user.uid);
      setSpecificUrl('');
    } catch (e) { setError(e.message); }
  }, [user]);

  const handleResetDefaults = useCallback(async () => {
    if (!user) return;
    if (window.confirm("Voulez-vous vraiment réinitialiser les paramètres du bot aux valeurs par défaut ?")) {
      const defaultAnalysis = {
        gatekeeperModel: 'gemini-2.5-flash-lite',
        mainModel: 'gemini-2.5-flash',
        expertModel: 'gemini-2.5-pro',
        mainAnalysisPrompt: DEFAULT_MAIN_PROMPT,
        gatekeeperVerbosityInstruction: DEFAULT_GATEKEEPER_INSTRUCTION,
        expertContextInstruction: DEFAULT_EXPERT_CONTEXT,
        rejectionVerdicts: DEFAULT_REJECTION_VERDICTS
      };

      setExclusionKeywords(DEFAULT_EXCLUSION_KEYWORDS);
      setAnalysisConfig(defaultAnalysis);
      setLogLimit(100);

      try {
        await updateUserConfig({
          exclusionKeywords: DEFAULT_EXCLUSION_KEYWORDS,
          'analysisConfig.gatekeeperModel': defaultAnalysis.gatekeeperModel,
          'analysisConfig.mainModel': defaultAnalysis.mainModel,
          'analysisConfig.expertModel': defaultAnalysis.expertModel,
          'analysisConfig.mainAnalysisPrompt': defaultAnalysis.mainAnalysisPrompt,
          'analysisConfig.gatekeeperVerbosityInstruction': defaultAnalysis.gatekeeperVerbosityInstruction,
          'analysisConfig.expertContextInstruction': defaultAnalysis.expertContextInstruction,
          'analysisConfig.rejectionVerdicts': defaultAnalysis.rejectionVerdicts,
          logLimit: 100
        }, user.uid);
      } catch (e) {
        console.error("Erreur lors du reset:", e);
        setError(e.message);
      }
    }
  }, [user]);

  return {
    configStatus, error, setError,
    scanConfig, setScanConfig,
    exclusionKeywords, setExclusionKeywords,
    analysisConfig, setAnalysisConfig,
    availableModels,
    logLimit, setLogLimit,
    botStatus, // Exposé pour affichage dynamique du statut
    isRefreshing, isCleaning, isReanalyzingAll, isScanningUrl, isPaused,
    saveConfig,
    handleManualRefresh, handleManualCleanup,
    handleRelaunchAll, handleScanSpecificUrl,
    handleResetDefaults
  };
};
