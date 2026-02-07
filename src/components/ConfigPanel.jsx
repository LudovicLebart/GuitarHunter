import React, { useState, useMemo } from 'react';
import { Search, Sparkles, RotateCcw, BrainCircuit, Trash2, Plus, RefreshCw, X, AlertCircle, Settings, MapPin } from 'lucide-react';
import { useBotConfigContext } from '../context/BotConfigContext';
import { useCitiesContext } from '../context/CitiesContext';
import CollapsibleSection from './CollapsibleSection';

// Sous-composant pour la section de recherche Facebook
const FacebookSearchSection = () => {
  const {
    scanConfig, setScanConfig, saveConfig,
    handleScanSpecificUrl, isScanningUrl
  } = useBotConfigContext();
  
  const [specificUrl, setSpecificUrl] = useState('');

  return (
    <div className="space-y-3">
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
    handleToggleScannable(city.docId, false); 
    setSearchTerm('');
  };

  const removeCityFromWhitelist = (city) => {
    handleToggleScannable(city.docId, true);
  };

  return (
    <div className="pt-2">
      {/* cytiListUI: Affiche les villes sélectionnées */}
      <div className="space-y-2 mb-3">
        {scannableCities.map(city => (
          <div key={city.docId} className="flex items-center justify-between bg-blue-50 p-2 rounded-lg text-xs border border-blue-100">
            <span className="font-bold text-blue-700">{city.name}</span>
            <button onClick={() => removeCityFromWhitelist(city)} className="text-blue-400 hover:text-rose-600 p-1">
              <X size={14} />
            </button>
          </div>
        ))}
        {scannableCities.length === 0 && <p className="text-[10px] text-slate-400 italic text-center py-2">Aucune ville sélectionnée.</p>}
      </div>

      {/* Champ de recherche et suggestions */}
      <div className="relative">
        <input 
          type="text"
          placeholder="Ajouter une ville..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full p-2 bg-slate-50 border border-slate-200 rounded-lg text-xs"
        />
        {suggestions.length > 0 && (
          <div className="absolute z-10 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-40 overflow-y-auto">
            {suggestions.map(suggestion => (
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

  const handleTextChange = (setter, fieldName, value) => {
    setter(value);
  };

  const handleBlur = (fieldName, value) => {
      saveConfig({ [fieldName]: value });
  };

  return (
    <div className="space-y-4 pt-2">
      <div className="flex items-center justify-between mb-2">
        <button
            onClick={handleRelaunchAll}
            disabled={isReanalyzingAll}
            className={`flex-grow mr-2 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all ${isReanalyzingAll ? 'bg-purple-100 text-purple-600' : 'bg-purple-50 text-purple-600 hover:bg-purple-100 border border-purple-100'}`}
        >
            <BrainCircuit size={14} className={isReanalyzingAll ? "animate-pulse" : ""} />
            {isReanalyzingAll ? 'Analyse...' : 'Relancer Analyses'}
        </button>
        
        <button 
          onClick={handleResetDefaults}
          className="text-[9px] font-bold text-slate-400 hover:text-blue-600 flex items-center gap-1 transition-colors px-2"
          title="Réinitialiser"
        >
          <RotateCcw size={10} /> Reset
        </button>
      </div>

      <div className="space-y-4">
        {/* Section Principale : Règles Métier */}
        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Identité du Bot (Persona)</label>
            <p className="text-[9px] text-slate-400 mb-2">Qui est l'IA ? (ex: "Tu es un expert luthier...")</p>
            <textarea
            value={prompt}
            onChange={(e) => handleTextChange(setPrompt, 'prompt', e.target.value)}
            onBlur={(e) => handleBlur('prompt', e.target.value)}
            className="w-full p-3 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-purple-500 outline-none transition-all h-24 font-mono text-slate-600"
            placeholder="Tu es un expert..."
            />
        </div>

        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Règles de Verdict (Critères)</label>
            <p className="text-[9px] text-slate-400 mb-2">Définissez quand une guitare est une "Pépite" ou un "Rejet".</p>
            <textarea
            value={verdictRules}
            onChange={(e) => handleTextChange(setVerdictRules, 'verdictRules', e.target.value)}
            onBlur={(e) => handleBlur('verdictRules', e.target.value)}
            className="w-full p-3 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-purple-500 outline-none transition-all h-32 font-mono text-slate-600"
            />
        </div>

        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Style de Réponse</label>
            <p className="text-[9px] text-slate-400 mb-2">Ton et format des explications.</p>
            <textarea
            value={reasoningInstruction}
            onChange={(e) => handleTextChange(setReasoningInstruction, 'reasoningInstruction', e.target.value)}
            onBlur={(e) => handleBlur('reasoningInstruction', e.target.value)}
            className="w-full p-3 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-purple-500 outline-none transition-all h-20 font-mono text-slate-600"
            />
        </div>

        {/* Section Avancée Masquée */}
        <CollapsibleSection title="Avancé">
            <div className="space-y-4 pt-2">
                <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                    <label className="text-[10px] font-bold text-slate-500 uppercase block mb-2">Template Utilisateur</label>
                    <p className="text-[9px] text-slate-400 mb-2">Structure du message envoyé à l'IA.</p>
                    <textarea
                    value={userPrompt}
                    onChange={(e) => handleTextChange(setUserPrompt, 'userPrompt', e.target.value)}
                    onBlur={(e) => handleBlur('userPrompt', e.target.value)}
                    className="w-full p-3 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-slate-400 outline-none transition-all h-24 font-mono text-slate-500"
                    />
                </div>
            </div>
        </CollapsibleSection>
      </div>
    </div>
  );
};


const ConfigPanel = ({ showConfig }) => {
  if (!showConfig) return null;

  return (
    <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200 space-y-2 animate-in fade-in slide-in-from-top-4 duration-300 max-h-[85vh] overflow-y-auto custom-scrollbar">
      <h3 className="text-xs font-black uppercase tracking-widest text-slate-400 sticky top-0 bg-white pb-2 z-10 border-b border-slate-50 mb-2">Paramètres</h3>
      
      <CollapsibleSection title="Recherche Facebook">
        <FacebookSearchSection />
      </CollapsibleSection>

      <CollapsibleSection title="Villes & Zones">
        <CityManagementSection />
      </CollapsibleSection>

      <CollapsibleSection title="Intelligence Artificielle">
        <AiConfigSection />
      </CollapsibleSection>

    </div>
  );
};

export default ConfigPanel;
