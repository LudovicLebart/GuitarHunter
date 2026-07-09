import React, { useState, useEffect, useMemo } from 'react';
import { Search, Sparkles, RotateCcw, BrainCircuit, Trash2, Plus, RefreshCw, X, AlertCircle, Settings, MapPin, ArrowUp, ArrowDown, Maximize2, Minimize2, Save, Terminal } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useBotConfigContext } from '../context/BotConfigContext';
import { useCitiesContext } from '../context/CitiesContext';

import CollapsibleSection from './CollapsibleSection';
import LogViewer from './LogViewer';

// --- COMPOSANT ÉDITEUR DE LISTE ---
const PromptListEditor = ({ items, onChange, onSave, placeholder = "Nouvelle instruction..." }) => {
  const safeItems = useMemo(() => Array.isArray(items) ? items : [], [items]);

  useEffect(() => {
    const needsSplit = safeItems.some(item => typeof item === 'string' && (item.includes('\n') || item.includes('\\n')));
    if (needsSplit) {
      const splitItems = safeItems.flatMap(item => (typeof item !== 'string') ? item : item.split(/\\n|\r?\n/));
      const cleanItems = splitItems.map(i => i ? i.trim() : "").filter(i => i !== "");
      if (JSON.stringify(cleanItems) !== JSON.stringify(safeItems)) {
        onChange(cleanItems);
      }
    }
  }, [safeItems, onChange]);

  const handleChange = (index, value) => {
    const newItems = [...safeItems];
    if (value.includes('\n')) {
      const lines = value.split(/\r?\n/);
      newItems.splice(index, 1, ...lines);
    } else {
      newItems[index] = value;
    }
    onChange(newItems);
  };

  const handleBlur = () => {
    const cleanItems = safeItems.filter(item => item && item.trim() !== "");
    if (JSON.stringify(cleanItems) !== JSON.stringify(safeItems)) {
      onChange(cleanItems);
    }
    onSave(cleanItems);
  };

  const moveItem = (index, direction) => {
    const newItems = [...safeItems];
    if (direction === 'up' && index > 0) {
      [newItems[index], newItems[index - 1]] = [newItems[index - 1], newItems[index]];
    } else if (direction === 'down' && index < newItems.length - 1) {
      [newItems[index], newItems[index + 1]] = [newItems[index + 1], newItems[index]];
    }
    onChange(newItems);
    onSave(newItems);
  };

  const deleteItem = (index) => {
    const newItems = safeItems.filter((_, i) => i !== index);
    onChange(newItems);
    onSave(newItems);
  };

  const addItem = () => {
    const newItems = [...safeItems, ""];
    onChange(newItems);
  };

  return (
    <div className="space-y-4">
      {safeItems.map((item, index) => (
        <div key={index} className="flex items-start gap-3 group animate-in fade-in slide-in-from-left-2 duration-200">
          <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity pt-2">
            <button onClick={() => moveItem(index, 'up')} disabled={index === 0} className="text-slate-500 hover:text-blue-400 disabled:opacity-0 transition-colors"><ArrowUp size={14} /></button>
            <button onClick={() => moveItem(index, 'down')} disabled={index === safeItems.length - 1} className="text-slate-500 hover:text-blue-400 disabled:opacity-0 transition-colors"><ArrowDown size={14} /></button>
          </div>
          <textarea
            value={item}
            onChange={(e) => handleChange(index, e.target.value)}
            onBlur={handleBlur}
            className="flex-grow p-4 bg-slate-900/50 border border-slate-800 rounded-xl text-[13px] focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 outline-none transition-all font-mono text-slate-200 resize-none overflow-hidden min-h-[80px] leading-relaxed shadow-inner"
            rows={Math.max(2, Math.ceil((item || "").length / 60))}
            placeholder={placeholder}
          />
          <button onClick={() => deleteItem(index)} className="text-slate-600 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity p-2 pt-3"><Trash2 size={16} /></button>
        </div>
      ))}
      <button
        onClick={addItem}
        className="w-full py-4 border-2 border-dashed border-slate-800 rounded-xl text-slate-500 hover:border-purple-500/50 hover:text-purple-400 hover:bg-purple-500/5 transition-all flex items-center justify-center gap-3 text-xs font-black uppercase tracking-widest mt-2"
      >
        <Plus size={16} /> Ajouter une ligne d'instruction
      </button>
    </div>
  );
};

// --- SOUS-COMPOSANTS ---

const FacebookSearchSection = () => {
  const { scanConfig, setScanConfig, saveConfig, handleScanSpecificUrl, isScanningUrl, handleManualRefresh, isRefreshing } = useBotConfigContext();
  const [specificUrl, setSpecificUrl] = useState('');

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 flex items-center gap-2">
            Rayon (km)
            {scanConfig.distance === 0 && <span className="text-blue-400 normal-case tracking-normal font-semibold">— Nom strict (Recommandé)</span>}
          </label>
          <input type="number" value={scanConfig.distance} onChange={(e) => setScanConfig({ ...scanConfig, distance: Number(e.target.value) })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" />
          {scanConfig.distance === 0 && <p className="text-[10px] text-slate-500 mt-1.5 leading-relaxed">Seules les annonces dont la ville correspond exactement au nom scanné sont conservées.</p>}
        </div>
        <div><label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Max Annonces</label><input type="number" value={scanConfig.max_ads} onChange={(e) => setScanConfig({ ...scanConfig, max_ads: Number(e.target.value) })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" /></div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div><label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Prix Min ($)</label><input type="number" value={scanConfig.min_price} onChange={(e) => setScanConfig({ ...scanConfig, min_price: Number(e.target.value) })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" /></div>
        <div><label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Prix Max ($)</label><input type="number" value={scanConfig.max_price} onChange={(e) => setScanConfig({ ...scanConfig, max_price: Number(e.target.value) })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" /></div>
      </div>
      <div><label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Fréquence Scan (min)</label><input type="number" value={scanConfig.frequency} onChange={(e) => setScanConfig({ ...scanConfig, frequency: Number(e.target.value) })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" /></div>
      <div><label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1.5 block">Mots-clés de recherche</label><input type="text" value={scanConfig.search_query} onChange={(e) => setScanConfig({ ...scanConfig, search_query: e.target.value })} onBlur={() => saveConfig({ scanConfig })} className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 focus:ring-2 focus:ring-blue-500/30 outline-none" /></div>
      
      <div className="pt-2">
        <button 
          onClick={handleManualRefresh}
          disabled={isRefreshing}
          className={`w-full py-4 rounded-xl text-xs font-black uppercase tracking-widest flex items-center justify-center gap-3 transition-all ${isRefreshing ? 'bg-blue-500/20 text-blue-400 cursor-not-allowed' : 'bg-blue-600 text-white hover:bg-blue-500 shadow-lg shadow-blue-900/40'}`}
        >
          <RefreshCw size={18} className={isRefreshing ? "animate-spin" : ""} />
          {isRefreshing ? 'Scan en cours...' : 'Lancer le Scan'}
        </button>
      </div>

      <div className="pt-4 border-t border-slate-800/50">
        <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 block">Scan d'URL Direct</label>
        <div className="flex gap-2">
          <input type="text" placeholder="URL Facebook Marketplace..." value={specificUrl} onChange={(e) => setSpecificUrl(e.target.value)} className="flex-grow p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 outline-none focus:ring-2 focus:ring-blue-500/30" />
          <button onClick={() => handleScanSpecificUrl(specificUrl, setSpecificUrl)} disabled={!specificUrl || isScanningUrl} className="bg-blue-600 text-white px-4 py-2 rounded-xl text-xs font-bold hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 transition-all flex items-center justify-center">
            {isScanningUrl ? <RefreshCw size={16} className="animate-spin" /> : <Search size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
};

const CityManagementSection = () => {
  const { cities, handleToggleScannable, handleAddCity, isAddingCity } = useCitiesContext();
  const [searchTerm, setSearchTerm] = useState('');
  const scannableCities = useMemo(() => cities.filter(c => c.isScannable), [cities]);
  const suggestions = useMemo(() => searchTerm ? cities.filter(c => !c.isScannable && c.name.toLowerCase().includes(searchTerm.toLowerCase()) && c.id) : [], [searchTerm, cities]);
  const addCityToWhitelist = (city) => { handleToggleScannable(city.docId, false); setSearchTerm(''); };
  const removeCityFromWhitelist = (city) => { handleToggleScannable(city.docId, true); };
  const handleSaveCity = async () => {
    const cityToAdd = searchTerm.trim();
    if (!cityToAdd || isAddingCity) return;
    await handleAddCity(cityToAdd);
    setSearchTerm('');
  };
  return (
    <div className="pt-2 space-y-4">
      <div className="space-y-2">
        <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest mb-1 block">Villes Actives</label>
        <div className="flex flex-wrap gap-2">
          {scannableCities.map(city => (
            <div key={city.docId} className="flex items-center gap-2 bg-blue-500/10 px-3 py-1.5 rounded-full text-xs border border-blue-500/30 group">
              <span className="font-bold text-blue-400">{city.name}</span>
              <button onClick={() => removeCityFromWhitelist(city)} className="text-blue-500/50 hover:text-rose-500 transition-colors">
                <X size={14} />
              </button>
            </div>
          ))}
          {scannableCities.length === 0 && (
            <p className="w-full text-[11px] text-slate-500 italic py-4 text-center bg-slate-900/30 rounded-xl border border-dashed border-slate-800">
              Aucune ville configurée pour le scan.
            </p>
          )}
        </div>
      </div>

      <div className="relative pt-2 border-t border-slate-800/50">
        <div className="flex items-center justify-between mb-2">
          <label className="text-[10px] font-black text-slate-500 uppercase tracking-widest block">Ajouter une zone</label>
          <span className="text-[9px] text-slate-600 font-bold uppercase tracking-tight">Taper le nom et cliquer sur + pour ajouter</span>
        </div>
        <div className="flex gap-2">
          <div className="relative flex-grow">
            <input
              type="text"
              placeholder="Rechercher une ville..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full p-3 bg-slate-900/50 border border-slate-800 rounded-xl text-xs text-slate-200 outline-none focus:ring-2 focus:ring-blue-500/30"
            />
            {suggestions.length > 0 && (
              <div className="absolute z-10 w-full mt-2 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl max-h-48 overflow-y-auto overflow-x-hidden scrollbar-dark">
                {suggestions.map(suggestion => (
                  <div key={suggestion.docId} onClick={() => addCityToWhitelist(suggestion)} className="p-3 text-xs text-slate-300 hover:bg-slate-700 hover:text-white cursor-pointer transition-colors border-b border-slate-700/50 last:border-0">
                    {suggestion.name}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={handleSaveCity}
            disabled={!searchTerm.trim() || isAddingCity}
            className={`p-3 rounded-xl border transition-all ${isAddingCity ? 'bg-blue-500/10 text-blue-400 border-blue-500/20 animate-pulse' : 'bg-slate-900/50 text-blue-400 border-slate-800 hover:bg-slate-800 hover:border-slate-700'}`}
          >
            {isAddingCity ? <RefreshCw size={16} className="animate-spin" /> : <Plus size={16} />}
          </button>
        </div>
      </div>


    </div>
  );
};

const ExclusionKeywordsSection = () => {
  const { exclusionKeywords, setExclusionKeywords, saveConfig } = useBotConfigContext();
  return (
    <div className="pt-2 space-y-4">
      <div className="bg-rose-500/5 p-5 rounded-3xl border border-rose-500/10">
        <label className="text-[11px] font-black text-rose-500 uppercase tracking-widest block mb-1">Mots-clés d'Exclusion</label>
        <p className="text-[10px] text-slate-500 mb-5 leading-relaxed">Si l'un de ces termes est détecté dans le titre ou la description, l'annonce est immédiatement écartée.</p>
        <PromptListEditor items={exclusionKeywords} onChange={setExclusionKeywords} onSave={(val) => saveConfig({ exclusionKeywords: val })} placeholder="Ex: Stagg, brisé, pour pièces..." />
      </div>
    </div>
  );
};

const AiConfigSection = () => {
  const { analysisConfig, setAnalysisConfig, saveConfig, handleResetDefaults, handleRelaunchAll, isReanalyzingAll, availableModels } = useBotConfigContext();

  const handleAnalysisConfigChange = (field, value) => {
    setAnalysisConfig(prev => ({ ...prev, [field]: value }));
  };

  // Fallback si la liste n'est pas encore chargée
  const models = availableModels.length > 0 ? availableModels : [
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview"
  ];

  return (
    <div className="space-y-6 pt-2">
      <div className="flex items-center gap-3">
        <button onClick={handleRelaunchAll} disabled={isReanalyzingAll} className={`flex-grow flex items-center justify-center gap-3 px-4 py-3 rounded-xl text-[11px] font-black uppercase tracking-widest transition-all ${isReanalyzingAll ? 'bg-purple-500/20 text-purple-400 cursor-not-allowed' : 'bg-purple-600 text-white hover:bg-purple-500 shadow-lg shadow-purple-900/40'}`}><BrainCircuit size={18} className={isReanalyzingAll ? "animate-pulse" : ""} />{isReanalyzingAll ? 'Traitement...' : 'Relancer Analyses'}</button>
        <button onClick={handleResetDefaults} className="w-12 h-12 flex items-center justify-center bg-slate-800 text-slate-400 hover:text-blue-400 rounded-xl border border-slate-700 transition-all" title="Réinitialiser par défaut"><RotateCcw size={18} /></button>
      </div>

      <div className="space-y-5">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-800">
            <label className="text-[10px] font-black text-purple-400 uppercase tracking-widest block mb-3">Modèle Portier</label>
            <select value={analysisConfig.gatekeeperModel} onChange={(e) => handleAnalysisConfigChange('gatekeeperModel', e.target.value)} onBlur={() => saveConfig({ 'analysisConfig.gatekeeperModel': analysisConfig.gatekeeperModel })} className="w-full p-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 outline-none focus:ring-2 focus:ring-purple-500/30">
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-800">
            <label className="text-[10px] font-black text-purple-400 uppercase tracking-widest block mb-3">Modèle Analyste</label>
            <select value={analysisConfig.mainModel || 'gemini-3.5-flash'} onChange={(e) => handleAnalysisConfigChange('mainModel', e.target.value)} onBlur={() => saveConfig({ 'analysisConfig.mainModel': analysisConfig.mainModel })} className="w-full p-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 outline-none focus:ring-2 focus:ring-purple-500/30">
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div className="bg-slate-900/50 p-4 rounded-2xl border border-slate-800">
            <label className="text-[10px] font-black text-purple-400 uppercase tracking-widest block mb-3">Modèle Expert</label>
            <select value={analysisConfig.expertModel} onChange={(e) => handleAnalysisConfigChange('expertModel', e.target.value)} onBlur={() => saveConfig({ 'analysisConfig.expertModel': analysisConfig.expertModel })} className="w-full p-2.5 bg-slate-900 border border-slate-700 rounded-xl text-xs text-slate-200 outline-none focus:ring-2 focus:ring-purple-500/30">
              {models.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        </div>

        <div className="bg-slate-900/80 p-5 rounded-3xl border border-slate-800/80">
          <label className="text-[11px] font-black text-purple-500 uppercase tracking-widest block mb-1">Prompt Principal</label>
          <p className="text-[10px] text-slate-500 mb-5 leading-relaxed">Instructions fondamentales partagées par tous les agents d'analyse.</p>
          <PromptListEditor items={analysisConfig.mainAnalysisPrompt} onChange={(val) => handleAnalysisConfigChange('mainAnalysisPrompt', val)} onSave={(val) => saveConfig({ 'analysisConfig.mainAnalysisPrompt': val })} placeholder="Ex: Tu es un expert en guitares..." />
        </div>

        <div className="bg-slate-900/80 p-5 rounded-3xl border border-slate-800/80">
          <label className="text-[11px] font-black text-purple-500 uppercase tracking-widest block mb-1">Instruction Portier</label>
          <p className="text-[10px] text-slate-500 mb-5 leading-relaxed">Règles de sortie spécifiques pour l'agent de premier niveau.</p>
          <PromptListEditor items={analysisConfig.gatekeeperVerbosityInstruction} onChange={(val) => handleAnalysisConfigChange('gatekeeperVerbosityInstruction', val)} onSave={(val) => saveConfig({ 'analysisConfig.gatekeeperVerbosityInstruction': val })} placeholder="Ex: Sois bref..." />
        </div>

        <div className="bg-slate-900/80 p-5 rounded-3xl border border-slate-800/80 border-l-4 border-l-rose-500/50">
          <label className="text-[11px] font-black text-rose-500 uppercase tracking-widest block mb-1">Coupe-Circuits (Reject)</label>
          <p className="text-[10px] text-slate-500 mb-5 leading-relaxed">Si le Portier renvoie l'un de ces statuts, l'analyse s'arrête immédiatement.</p>
          <PromptListEditor items={analysisConfig.rejectionVerdicts} onChange={(val) => handleAnalysisConfigChange('rejectionVerdicts', val)} onSave={(val) => saveConfig({ 'analysisConfig.rejectionVerdicts': val })} placeholder="Ajouter un verdict (ex: BAD_DEAL)" />
        </div>
      </div>
    </div>
  );
};

const LogsConfigSection = () => {
  const { logLimit, setLogLimit, saveConfig } = useBotConfigContext();

  return (
    <div className="pt-2 space-y-4">
      <div className="bg-slate-900/50 p-5 rounded-3xl border border-slate-800">
        <label className="text-[11px] font-black text-slate-400 uppercase tracking-widest block mb-1">Limite Temporaire de Logs</label>
        <p className="text-[10px] text-slate-500 mb-5 leading-relaxed">Nombre maximum de lignes conservées en mémoire pour l'affichage temps-réel.</p>
        <div className="flex items-center gap-4">
          <input
            type="range"
            min="10"
            max="500"
            step="10"
            value={logLimit}
            onChange={(e) => setLogLimit(Number(e.target.value))}
            onBlur={() => saveConfig({ logLimit: Number(logLimit) })}
            className="flex-grow h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <span className="min-w-[40px] text-right font-mono text-xs text-blue-400 font-bold">{logLimit}</span>
        </div>
      </div>
    </div>
  );
};

const ConfigPanel = ({ showConfig, onClose }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showLogs, setShowLogs] = useState(false);

  if (!showConfig) return null;

  const panelContent = (
    <div className={`bg-slate-950 shadow-2xl border-l border-slate-800 flex flex-col transition-all duration-300 ease-in-out ${isExpanded ? 'w-[900px] max-w-[95vw]' : 'w-full lg:w-[500px]'}`}>
      <div className="flex items-center justify-between p-6 border-b border-slate-800 bg-slate-900 sticky top-0 z-20">
        <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400 flex items-center gap-3">
          <Settings size={16} className="text-blue-500" />
          Paramètres Système
        </h3>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowLogs(!showLogs)} className={`w-8 h-8 flex items-center justify-center rounded-lg transition-all ${showLogs ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/20' : 'text-slate-400 hover:text-white hover:bg-slate-800'}`} title="Visionneuse de logs"><Terminal size={16} /></button>
          <button onClick={() => setIsExpanded(!isExpanded)} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-blue-400 hover:bg-slate-800 rounded-lg transition-all hidden lg:block">{isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
          <button onClick={onClose} className="w-8 h-8 flex items-center justify-center text-slate-400 hover:text-rose-500 hover:bg-slate-800 rounded-lg transition-all"><X size={20} /></button>
        </div>
      </div>
      <div className="flex-grow overflow-y-auto scrollbar-dark p-6 space-y-4">
        <CollapsibleSection title="Scraping & Facebook"><FacebookSearchSection /></CollapsibleSection>
        <CollapsibleSection title="Géo-Localisation"><CityManagementSection /></CollapsibleSection>
        <CollapsibleSection title="Nettoyage & Mots-clés"><ExclusionKeywordsSection /></CollapsibleSection>
        <CollapsibleSection title="Intelligence Artificielle V2"><AiConfigSection /></CollapsibleSection>
        <CollapsibleSection title="Système & Maintenance"><LogsConfigSection /></CollapsibleSection>
      </div>
      {showLogs && <LogViewer onClose={() => setShowLogs(false)} />}
    </div>
  );

  if (window.innerWidth < 1024) {
    return (
      <div className="bg-slate-900 p-6 rounded-3xl shadow-2xl border border-slate-800 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300 max-h-[85vh] overflow-y-auto scrollbar-dark relative">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-[11px] font-black uppercase tracking-[0.2em] text-slate-400">Paramètres</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-rose-500 transition-colors"><X size={20} /></button>
        </div>
        <CollapsibleSection title="Scraping"><FacebookSearchSection /></CollapsibleSection>
        <CollapsibleSection title="Villes"><CityManagementSection /></CollapsibleSection>
        <CollapsibleSection title="Filtres"><ExclusionKeywordsSection /></CollapsibleSection>
        <CollapsibleSection title="IA"><AiConfigSection /></CollapsibleSection>
        <CollapsibleSection title="Logs"><LogsConfigSection /></CollapsibleSection>
        <button onClick={() => setShowLogs(!showLogs)} className="w-full mt-4 py-3 bg-slate-800 text-slate-200 rounded-xl text-xs font-bold flex items-center justify-center gap-2 hover:bg-slate-700 transition-all border border-slate-700"><Terminal size={14} /> {showLogs ? 'Masquer Logs' : 'Logs Serveur'}</button>
        {showLogs && <LogViewer onClose={() => setShowLogs(false)} />}
      </div>
    );
  }

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end pointer-events-none">
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm pointer-events-auto transition-opacity opacity-100" onClick={onClose} />
      <div className="relative z-10 pointer-events-auto h-full animate-in slide-in-from-right duration-300 flex">
        {panelContent}
      </div>
    </div>,
    document.body
  );
};

export default ConfigPanel;
