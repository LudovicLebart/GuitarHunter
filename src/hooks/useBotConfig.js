import { useState, useEffect, useCallback } from 'react';
import { doc, onSnapshot, setDoc, deleteField } from 'firebase/firestore';
import { db } from '../services/firebase';
import promptsData from '../../prompts.json';

const PYTHON_USER_ID = "00737242777130596039";
const APP_ID = "c_5d118e719dbddbfc_index.html-217";

const DEFAULT_PROMPT = promptsData.system_prompt;
const DEFAULT_VERDICT_RULES = promptsData.verdict_rules;
const DEFAULT_REASONING_INSTRUCTION = promptsData.reasoning_instruction;
const DEFAULT_USER_PROMPT = promptsData.user_prompt;

export const useBotConfig = (user) => {
  const [configStatus, setConfigStatus] = useState({ status: 'pending', msg: 'En attente' });
  const [error, setError] = useState(null);
  
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [verdictRules, setVerdictRules] = useState(DEFAULT_VERDICT_RULES);
  const [reasoningInstruction, setReasoningInstruction] = useState(DEFAULT_REASONING_INSTRUCTION);
  const [userPrompt, setUserPrompt] = useState(DEFAULT_USER_PROMPT);
  const [scanConfig, setScanConfig] = useState({
      max_ads: 5, frequency: 60, location: 'montreal', distance: 60, min_price: 0, max_price: 150, search_query: "electric guitar"
  });

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isCleaning, setIsCleaning] = useState(false);
  const [isReanalyzingAll, setIsReanalyzingAll] = useState(false);
  const [isScanningUrl, setIsScanningUrl] = useState(false);

  useEffect(() => {
    if (!user) return;
    const userDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID);
    
    const unsubscribe = onSnapshot(userDocRef, (docSnap) => {
      if (docSnap.exists()) {
        setConfigStatus({ status: 'success', msg: 'Dossier Python trouvé' });
        const data = docSnap.data();
        
        if (data.prompt) setPrompt(data.prompt);
        if (data.verdictRules) setVerdictRules(data.verdictRules);
        if (data.reasoningInstruction) setReasoningInstruction(data.reasoningInstruction);
        if (data.userPrompt) setUserPrompt(data.userPrompt);
        if (data.scanConfig) setScanConfig(prev => ({ ...prev, ...data.scanConfig }));

        if (data.scanError) {
          setError(data.scanError);
        } else {
          if (error && error.startsWith("Ville")) {
             setError(null);
          }
        }
      } else {
        setConfigStatus({ status: 'error', msg: "Dossier Python introuvable" });
      }
    }, (e) => {
      setConfigStatus({ status: 'error', msg: e.message });
    });

    return () => unsubscribe();
  }, [user, error]);

  const saveConfig = useCallback(async (newVal) => {
    try {
      const userDocRef = doc(db, 'artifacts', APP_ID, 'users', PYTHON_USER_ID);
      await setDoc(userDocRef, newVal, { merge: true });
    } catch (e) { setError("Erreur de sauvegarde"); }
  }, []);

  const handleManualRefresh = useCallback(async () => {
    setIsRefreshing(true);
    await saveConfig({ forceRefresh: Date.now(), scanError: deleteField() });
    setTimeout(() => setIsRefreshing(false), 5000);
  }, [saveConfig]);

  const handleManualCleanup = useCallback(async () => {
    setIsCleaning(true);
    await saveConfig({ forceCleanup: Date.now() });
    setTimeout(() => setIsCleaning(false), 5000);
  }, [saveConfig]);

  const handleRelaunchAll = useCallback(async () => {
    if (window.confirm("⚠️ ATTENTION : Voulez-vous vraiment relancer l'analyse IA pour TOUTES les annonces ?")) {
        setIsReanalyzingAll(true);
        try {
            await saveConfig({ forceReanalyzeAll: Date.now() });
            setTimeout(() => setIsReanalyzingAll(false), 5000);
        } catch (e) {
            setError("Erreur lors de la demande de ré-analyse globale.");
            setIsReanalyzingAll(false);
        }
    }
  }, [saveConfig]);

  const handleScanSpecificUrl = useCallback(async (specificUrl, setSpecificUrl) => {
    if (!specificUrl) return;
    setIsScanningUrl(true);
    try {
      await saveConfig({ scanSpecificUrl: specificUrl });
      setSpecificUrl('');
      setTimeout(() => setIsScanningUrl(false), 5000);
    } catch (e) {
      setError("Erreur lors de la demande de scan d'URL.");
      setIsScanningUrl(false);
    }
  }, [saveConfig]);

  const handleResetDefaults = useCallback(async () => {
    if (window.confirm("Voulez-vous vraiment réinitialiser les paramètres du bot aux valeurs par défaut ?")) {
      setPrompt(DEFAULT_PROMPT);
      setVerdictRules(DEFAULT_VERDICT_RULES);
      setReasoningInstruction(DEFAULT_REASONING_INSTRUCTION);
      setUserPrompt(DEFAULT_USER_PROMPT);
      await saveConfig({
        prompt: DEFAULT_PROMPT,
        verdictRules: DEFAULT_VERDICT_RULES,
        reasoningInstruction: DEFAULT_REASONING_INSTRUCTION,
        userPrompt: DEFAULT_USER_PROMPT
      });
    }
  }, [saveConfig]);

  return {
    configStatus,
    error,
    setError,
    prompt, setPrompt,
    verdictRules, setVerdictRules,
    reasoningInstruction, setReasoningInstruction,
    userPrompt, setUserPrompt,
    scanConfig, setScanConfig,
    isRefreshing,
    isCleaning,
    isReanalyzingAll,
    isScanningUrl,
    saveConfig,
    handleManualRefresh,
    handleManualCleanup,
    handleRelaunchAll,
    handleScanSpecificUrl,
    handleResetDefaults
  };
};
