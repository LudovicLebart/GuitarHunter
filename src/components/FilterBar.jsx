import React from 'react';
import { Search, List, Map as MapIcon } from 'lucide-react';

export const FilterBar = ({
  viewMode, setViewMode,
  filterType, setFilterType,
  searchQuery, setSearchQuery,
  level1Filter, setLevel1Filter,
  level2Filter, setLevel2Filter,
  level3Filter, setLevel3Filter,
  level1Options,
  level2Options,
  level3Options,
  counts = {} // Réception des compteurs
}) => {
  
  const getCount = (key) => {
      return counts[key] || 0;
  };

  return (
    <div className="bg-white p-4 rounded-3xl shadow-sm border border-slate-200 flex flex-wrap gap-4 items-center justify-between">
      <div className="flex-1 min-w-[200px] relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
        <input type="text" placeholder="Rechercher par modèle..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-10 pr-4 py-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all" />
      </div>
      <div className="flex bg-slate-100 p-1 rounded-2xl">
        <button onClick={() => setViewMode('LIST')} className={`p-2 rounded-xl transition-all ${viewMode === 'LIST' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}><List size={18} /></button>
        <button onClick={() => setViewMode('MAP')} className={`p-2 rounded-xl transition-all ${viewMode === 'MAP' ? 'bg-white shadow-sm text-blue-600' : 'text-slate-400 hover:text-slate-600'}`}><MapIcon size={18} /></button>
      </div>
      <div className="flex items-center gap-2 overflow-x-auto pb-1 w-full lg:w-auto">
        {['ALL', 'FAVORITES', 'PEPITE', 'GOOD_DEAL', 'FAIR', 'BAD_DEAL', 'REJECTED', 'ERROR'].map((type) => {
            const count = getCount(type);
            return (
                <button key={type} onClick={() => setFilterType(type)} className={`px-4 py-2 rounded-2xl text-xs font-bold whitespace-nowrap transition-all flex items-center gap-2 ${filterType === type ? 'bg-blue-600 text-white shadow-md' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>
                    <span>
                        {type === 'ALL' ? 'Toutes' : type === 'FAVORITES' ? 'Favoris' : type === 'PEPITE' ? 'Pépites' : type === 'GOOD_DEAL' ? 'Bonnes Affaires' : type === 'FAIR' ? 'Prix Juste' : type === 'BAD_DEAL' ? 'Trop Cher' : type === 'REJECTED' ? 'Rejetées' : 'Erreurs'}
                    </span>
                    {count > 0 && (
                        <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${filterType === type ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-600'}`}>
                            {count}
                        </span>
                    )}
                </button>
            );
        })}
      </div>
      <div className="w-full flex flex-wrap gap-2">
        <select value={level1Filter} onChange={(e) => setLevel1Filter(e.target.value)} className="p-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all">
          <option value="ALL">Type (Tous)</option>
          {level1Options.filter(o => o !== 'ALL').map(o => (
              <option key={o} value={o}>
                  {o.replace(/_/g, ' ')} {counts[o] > 0 ? `(${counts[o]})` : ''}
              </option>
          ))}
        </select>
        {level1Filter !== 'ALL' && level2Options.length > 1 && (
          <select value={level2Filter} onChange={(e) => setLevel2Filter(e.target.value)} className="p-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all animate-in fade-in slide-in-from-left-2">
            <option value="ALL">Sous-catégorie (Toutes)</option>
            {level2Options.filter(o => o !== 'ALL').map(o => (<option key={o} value={o}>{o.replace(/_/g, ' ')}</option>))}
          </select>
        )}
        {level2Filter !== 'ALL' && level3Options.length > 1 && (
          <select value={level3Filter} onChange={(e) => setLevel3Filter(e.target.value)} className="p-2.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-blue-500 outline-none transition-all animate-in fade-in slide-in-from-left-2">
            <option value="ALL">Modèle (Tous)</option>
            {level3Options.filter(o => o !== 'ALL').map(o => (<option key={o} value={o}>{o.replace(/_/g, ' ')}</option>))}
          </select>
        )}
      </div>
    </div>
  );
};
