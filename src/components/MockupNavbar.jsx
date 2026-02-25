import React from 'react';
import { Guitar, Activity, SlidersHorizontal, X, Settings } from 'lucide-react';

const StatusDot = ({ ok, label }) => (
    <div className="flex items-center gap-1.5 text-[11px] font-bold">
        <div className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-rose-400'}`} />
        <span className={ok ? 'text-slate-400' : 'text-rose-400'}>{label}</span>
    </div>
);

const MockupNavbar = ({ onOpenFilters, onOpenSettings, onClose, filterCount }) => (
    <nav className="sticky top-0 z-30 bg-slate-900/80 backdrop-blur-lg border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 h-16 flex items-center justify-between gap-4">

            {/* Logo */}
            <div className="flex items-center gap-3 shrink-0">
                <div className="bg-blue-600 p-2 rounded-xl text-white shadow-md shadow-blue-500/20">
                    <Guitar size={20} />
                </div>
                <div>
                    <h1 className="text-base font-black tracking-tight text-white leading-none">
                        GUITAR HUNTER <span className="text-blue-400">AI</span>
                    </h1>
                    <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest leading-none">
                        Scraper & Gemini Evaluator
                    </p>
                </div>
            </div>

            {/* Center: compact system statuses */}
            <div className="hidden md:flex items-center gap-4 flex-1 justify-center">
                <StatusDot ok={true} label="Auth" />
                <div className="w-px h-4 bg-slate-800" />
                <div className="flex items-center gap-1.5 text-[11px] font-bold">
                    <Activity size={12} className="text-blue-400 animate-pulse" />
                    <span className="text-blue-400">Scan en cours</span>
                </div>
                <div className="w-px h-4 bg-slate-800" />
                <StatusDot ok={true} label="DB · 517 ann." />
            </div>

            {/* Right: filters + settings + exit */}
            <div className="flex items-center gap-2 shrink-0">

                {/* Filters button */}
                <button
                    onClick={onOpenFilters}
                    className="flex items-center gap-2 px-3 h-9 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 text-xs font-bold hover:bg-slate-700 transition-all"
                >
                    <SlidersHorizontal size={14} />
                    <span className="hidden sm:inline">Filtres</span>
                    {filterCount > 0 && (
                        <span className="bg-blue-500 text-white text-[10px] font-black w-4 h-4 rounded-full flex items-center justify-center">
                            {filterCount}
                        </span>
                    )}
                </button>

                {/* Settings / Paramètres button (gear icon) */}
                <button
                    onClick={onOpenSettings}
                    className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-all"
                    title="Paramètres"
                >
                    <Settings size={16} />
                </button>

                {/* Exit Mockup */}
                <button
                    onClick={onClose}
                    className="flex items-center gap-2 px-3 h-9 rounded-xl bg-purple-600 text-white text-xs font-bold hover:bg-purple-500 transition-all border border-purple-500"
                >
                    <X size={14} />
                    <span className="hidden sm:inline">Quitter V2</span>
                </button>
            </div>
        </div>
    </nav>
);

export default MockupNavbar;
