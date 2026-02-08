import React, { useState, useEffect, useMemo } from 'react';
import { Search, Sparkles, RotateCcw, BrainCircuit, Trash2, Plus, RefreshCw, X, AlertCircle, Settings, MapPin, ArrowUp, ArrowDown, Maximize2, Minimize2 } from 'lucide-react';
import { createPortal } from 'react-dom';
import { useBotConfigContext } from '../context/BotConfigContext';
import { useCitiesContext } from '../context/CitiesContext';
import CollapsibleSection from './CollapsibleSection';

// --- COMPOSANT ÉDITEUR DE LISTE ---
const PromptListEditor = ({ items, onChange, onSave, placeholder = "Nouvelle instruction..." }) => {
  const safeItems = useMemo(() => Array.isArray(items) ? items : [], [items]);
  
  useEffect(() => {
    const needsSplit = safeItems.some(item => typeof item === 'string' && (item.includes('\n') || item.includes('\\n')));
    
    if (needsSplit) {
        const splitItems = safeItems.flatMap(item => {
            if (typeof item !== 'string') return item;
            return item.split(/\\n|\r?\n/);
        });
        
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
    <div className="space-y-3">
      {safeItems.map((item, index) => (
        <div key={index} className="flex items-start gap-2 group animate-in fade-in slide-in-from-left-2 duration-200">
          <div className="flex flex-col gap-1 opacity-0 group-hover:opacity-100 transition-opacity pt-2">
            <button 
              onClick={() => moveItem(index, 'up')} 
              disabled={index === 0}
              className="text-slate-300 hover:text-blue-500 disabled:opacity-0"
            >
              <ArrowUp size={14} />
            </button>
            <button 
              onClick={() => moveItem(index, 'down')} 
              disabled={index === safeItems.length - 1}
              className="text-slate-300 hover:text-blue-500 disabled:opacity-0"
            >
              <ArrowDown size={14} />
            </button>
          </div>
          
          <textarea
            value={item}
            onChange={(e) => handleChange(index, e.target.value)}
            onBlur={handleBlur}
            className="flex-grow p-3 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-purple-500 outline-none transition-all font-mono text-slate-600 resize-none overflow-hidden min-h-[60px] leading-relaxed shadow-sm"
            rows={Math.max(2, Math.ceil((item || "").length / 70))} 
            placeholder={placeholder}
          />
          
          <button 
            onClick={() => deleteItem(index)}
            className="text-slate-300 hover:text-rose-500 opacity-0 group-hover:opacity-100 transition-opacity p-2 pt-3"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      
      <button 
        onClick={addItem}
        className="w-full py-3 border-2 border-dashed border-slate-200 rounded-lg text-slate-400 hover:border-purple-300 hover:text-purple-500 hover:bg-purple-50 transition-all flex items-center justify-center gap-2 text-xs font-bold uppercase tracking-wider mt-2"
      >
        <Plus size={14} /> Ajouter une ligne
      </button>
    </div>
  );
};

// --- SOUS-COMPOSANTS ---

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

const CityManagementSection = () => {
  const { cities, handleToggleScannable } = useCitiesContext();
  const [searchTerm, setSearchTerm] = useState('');

  const scannableCities = useMemo(() => cities.filter(c => c.isScannable), [cities]);
  
  const suggestions = useMemo(() => {
    if (!searchTerm) return [];
    return cities.filter(c => 
      !c.isScannable && 
      c.name.toLowerCase().includes(searchTerm.toLowerCase()) &&
      c.id 
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

const AiConfigSection = () => {
  const {
    prompt, setPrompt,
    verdictRules, setVerdictRules,
    reasoningInstruction, setReasoningInstruction,
    saveConfig, handleResetDefaults, handleRelaunchAll, isReanalyzingAll
  } = useBotConfigContext();

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

      <div className="space-y-6">
        {/* Section Principale : Règles Métier */}
        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Identité du Bot (Persona)</label>
            <p className="text-[9px] text-slate-400 mb-3">Définissez ligne par ligne qui est l'IA et ses objectifs.</p>
            <PromptListEditor 
                items={prompt} 
                onChange={setPrompt} 
                onSave={(val) => saveConfig({ prompt: val })}
                placeholder="Ex: Tu es un expert..."
            />
        </div>

        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Règles de Verdict (Critères)</label>
            <p className="text-[9px] text-slate-400 mb-3">Une règle par ligne. L'ordre compte.</p>
            <PromptListEditor 
                items={verdictRules} 
                onChange={setVerdictRules} 
                onSave={(val) => saveConfig({ verdictRules: val })}
                placeholder="Ex: SI prix > 1000 ALORS..."
            />
        </div>

        <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
            <label className="text-[10px] font-bold text-purple-600 uppercase block mb-2">Style de Réponse</label>
            <p className="text-[9px] text-slate-400 mb-3">Instructions de ton et de formatage.</p>
            <PromptListEditor 
                items={reasoningInstruction} 
                onChange={setReasoningInstruction} 
                onSave={(val) => saveConfig({ reasoningInstruction: val })}
                placeholder="Ex: Sois concis..."
            />
        </div>
      </div>
    </div>
  );
};

const ConfigPanel = ({ showConfig, onClose }) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!showConfig) return null;

  const panelContent = (
    <div className={`bg-white shadow-2xl border-l border-slate-200 flex flex-col transition-all duration-300 ease-in-out ${isExpanded ? 'w-[900px] max-w-[95vw]' : 'w-full lg:w-[500px]'}`}>
      <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-white sticky top-0 z-20">
        <h3 className="text-xs font-black uppercase tracking-widest text-slate-400">Paramètres</h3>
        <div className="flex items-center gap-2">
            <button 
                onClick={() => setIsExpanded(!isExpanded)} 
                className="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors hidden lg:block"
                title={isExpanded ? "Réduire" : "Agrandir"}
            >
                {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button 
                onClick={onClose} 
                className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
            >
                <X size={18} />
            </button>
        </div>
      </div>
      
      <div className="flex-grow overflow-y-auto custom-scrollbar p-5 space-y-2">
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
    </div>
  );

  // Sur mobile/tablette, on garde le comportement "in-flow" (dans la colonne de gauche)
  // Sur desktop (lg), on utilise un Portal pour afficher le panneau en overlay ou drawer
  if (window.innerWidth < 1024) {
      return (
        <div className="bg-white p-5 rounded-3xl shadow-sm border border-slate-200 space-y-2 animate-in fade-in slide-in-from-top-4 duration-300 max-h-[85vh] overflow-y-auto custom-scrollbar relative">
            <button onClick={onClose} className="absolute top-4 right-4 text-slate-400 hover:text-rose-600"><X size={18} /></button>
            <h3 className="text-xs font-black uppercase tracking-widest text-slate-400 mb-4">Paramètres</h3>
            <CollapsibleSection title="Recherche Facebook"><FacebookSearchSection /></CollapsibleSection>
            <CollapsibleSection title="Villes & Zones"><CityManagementSection /></CollapsibleSection>
            <CollapsibleSection title="Intelligence Artificielle"><AiConfigSection /></CollapsibleSection>
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
