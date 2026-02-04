import React, { useState, useMemo } from 'react';
import { Search, Sparkles, RotateCcw, BrainCircuit, Trash2, Plus, RefreshCw, X, AlertCircle } from 'lucide-react';
import { useBotConfigContext } from '../context/BotConfigContext';
import { useCitiesContext } from '../context/CitiesContext';

// Sous-composant pour la section de recherche Facebook
const FacebookSearchSection = () => {
  const {
    scanConfig, setScanConfig, saveConfig,
    handleScanSpecificUrl, isScanningUrl
  } = useBotConfigContext();
  
  const [specificUrl, setSpecificUrl] = useState('');

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-blue-600 mb-2">
        <Search size={14} />
        <span className="text-[10px] font-black uppercase tracking-widest">Recherche Facebook</span>
      </div>
      
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[9px] font-bold text-slate-400 uppercase">Dist (km)</label>
          <input type="number" value={scanConfig.distance} onChange={(e) => setScanConfig({...scanConfig, distance: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
        </div>
        <div>
          <label className="text-[9px] font-bold text-slate-400 uppercase">Max Ads</label>
          <input type="number" value={scanConfig.max_ads} onChange={(e) => setScanConfig({...scanConfig, max_ads: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[9px] font-bold text-slate-400 uppercase">Min Price</label>
          <input type="number" value={scanConfig.min_price} onChange={(e) => setScanConfig({...scanConfig, min_price: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
        </div>
        <div>
          <label className="text-[9px] font-bold text-slate-400 uppercase">Max Price</label>
          <input type="number" value={scanConfig.max_price} onChange={(e) => setScanConfig({...scanConfig, max_price: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
        </div>
      </div>

      <div>
        <label className="text-[9px] font-bold text-slate-400 uppercase">Fréquence (min)</label>
        <input type="number" value={scanConfig.frequency} onChange={(e) => setScanConfig({...scanConfig, frequency: Number(e.target.value)})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
      </div>
      
      <div>
        <label className="text-[9px] font-bold text-slate-400 uppercase">Search Query</label>
        <input type="text" value={scanConfig.search_query} onChange={(e) => setScanConfig({...scanConfig, search_query: e.target.value})} onBlur={() => saveConfig({ scanConfig })} className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs" />
      </div>

      <div className="pt-3 border-t border-slate-100">
        <label className="text-[9px] font-bold text-slate-400 uppercase">Scan d'URL Spécifique</label>
        <div className="flex gap-2 mt-1">
          <input
            type="text"
            placeholder="Coller l'URL de l'annonce Facebook..."
            value={specificUrl}
            onChange={(e) => setSpecificUrl(e.target.value)}
            className="flex-grow p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs"
          />
          <button
            onClick={() => handleScanSpecificUrl(specificUrl, setSpecificUrl)}
            disabled={!specificUrl || isScanningUrl}
            className="bg-blue-500 text-white px-3 py-2 rounded-lg text-xs font-bold hover:bg-blue-600 disabled:bg-slate-300 flex items-center justify-center"
          >
            {isScanningUrl ? <RefreshCw size={14} className="animate-spin" /> : <Search size={14} />}
          </button>
        </div>
      </div>
    </div>
  );
};

// Sous-composant pour la gestion des villes
const CityManagementSection = () => {
  const { cities, handleToggleScannable } = useCitiesContext();
  const [searchTerm, setSearchTerm] = useState('');

  const scannableCities = useMemo(() => cities.filter(c => c.isScannable), [cities]);
  
  const suggestions = useMemo(() => {
    if (!searchTerm) return [];
    return cities.filter(c => 
      !c.isScannable && 
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) &&
      c.id // On ne peut ajouter que les villes qui ont un ID Facebook
    );
  }, [searchTerm, cities]);

  const addCityToWhitelist = (city) => {
    // On utilise docId pour l'update
    handleToggleScannable(city.docId, false); 
    setSearchTerm('');
  };

  const removeCityFromWhitelist = (city) => {
    // On utilise docId pour l'update
    handleToggleScannable(city.docId, true);
  };

  return (
    <div className="pt-4 border-t border-slate-100">
      <label className="text-[9px] font-bold text-slate-400 uppercase block mb-2">Villes à Scanner</label>
      
      {/* cytiListUI: Affiche les villes sélectionnées */}
      <div className="space-y-2 mb-3">
        {scannableCities.map(city => (
          // Utilisation de docId comme clé unique
          <div key={city.docId} className="flex items-center justify-between bg-blue-50 p-2 rounded-lg text-xs border border-blue-100">
            <span className="font-bold text-blue-700">{city.name}</span>
            <button onClick={() => removeCityFromWhitelist(city)} className="text-blue-400 hover:text-rose-600 p-1">
              <X size={14} />
            </button>
          </div>
        ))}
        {scannableCities.length === 0 && <p className="text-[10px] text-slate-400 italic text-center py-2">Aucune ville sélectionnée pour le scan.</p>}
      </div>

      {/* Champ de recherche et suggestions */}
      <div className="relative">
        <input 
          type="text"
          placeholder="Rechercher une ville à ajouter..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs"
        />
        {suggestions.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-40 overflow-y-auto">
            {suggestions.map(suggestion => (
              // Utilisation de docId comme clé unique
              <div 
                key={suggestion.docId}
                onClick={() => addCityToWhitelist(suggestion)}
                className="p-2 text-xs hover:bg-blue-50 cursor-pointer"
              >
                {suggestion.name}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

// Sous-composant pour la configuration de l'IA
const AiConfigSection = () => {
  const {
    prompt, setPrompt,
    userPrompt, setUserPrompt,
    verdictRules, setVerdictRules,
    reasoningInstruction, setReasoningInstruction,
    saveConfig, handleResetDefaults, handleRelaunchAll, isReanalyzingAll
  } = useBotConfigContext();

  return (
    <div className="space-y-3 pt-4 border-t border-slate-100">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2 text-purple-600">
          <Sparkles size={14} />
          <span className="text-[10px] font-black uppercase tracking-widest">Intelligence Artificielle</span>
        </div>
        <button 
          onClick={handleResetDefaults}
          className="text-[9px] font-bold text-slate-400 hover:text-blue-600 flex items-center gap-1 transition-colors"
          title="Réinitialiser aux valeurs par défaut"
        >
          <RotateCcw size={10} /> Reset
        </button>
      </div>

      <button
          onClick={handleRelaunchAll}
          disabled={isReanalyzingAll}
          className={`w-full mb-4 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all ${isReanalyzingAll ? 'bg-purple-100 text-purple-600' : 'bg-purple-50 text-purple-600 hover:bg-purple-100 border border-purple-100'}`}
      >
          <BrainCircuit size={16} className={isReanalyzingAll ? "animate-pulse" : ""} />
          {isReanalyzingAll ? 'Demande envoyée...' : 'Relancer TOUTES les analyses'}
      </button>

      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prompt Gemini</label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onBlur={() => saveConfig({ prompt })}
          className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24 italic"
        />
      </div>

      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Prompt Utilisateur (Template)</label>
        <textarea
          value={userPrompt}
          onChange={(e) => setUserPrompt(e.target.value)}
          onBlur={() => saveConfig({ userPrompt })}
          className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24 italic"
          placeholder="Utilisez {title}, {price}, {description} comme placeholders."
        />
      </div>

      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Règles de Verdict</label>
        <textarea
          value={verdictRules}
          onChange={(e) => setVerdictRules(e.target.value)}
          onBlur={() => saveConfig({ verdictRules })}
          className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
        />
      </div>

      <div>
        <label className="text-[10px] font-bold text-slate-400 uppercase block mb-1">Instruction de Raisonnement</label>
        <textarea
          value={reasoningInstruction}
          onChange={(e) => setReasoningInstruction(e.target.value)}
          onBlur={() => saveConfig({ reasoningInstruction })}
          className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:ring-2 focus:ring-blue-500 outline-none transition-all h-24"
        />
      </div>
    </div>
  );
};


const ConfigPanel = ({ showConfig }) => {
  if (!showConfig) return null;

  return (
    <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200 space-y-4 animate-in fade-in slide-in-from-top-4 duration-300">
      <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Paramètres</h3>
      
      <FacebookSearchSection />
      <CityManagementSection />
      <AiConfigSection />

    </div>
  );
};

export default ConfigPanel;
