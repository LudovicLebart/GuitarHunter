import React from 'react';
import { Guitar, Activity, SlidersHorizontal, X, Settings, Square, Power, SkipForward, PauseCircle, Trash2, RefreshCw, LogOut } from 'lucide-react';
import { useBotConfigContext } from '../context/BotConfigContext';
import { useAuth } from '../hooks/useAuth';
import { triggerStopScan, triggerStopBot, triggerStartBot } from '../services/firestoreService';

const StatusDot = ({ ok, label }) => (
    <div className="flex items-center gap-1.5 text-[11px] font-bold">
        <div className={`w-1.5 h-1.5 rounded-full ${ok ? 'bg-emerald-400' : 'bg-rose-400'}`} />
        <span className={ok ? 'text-slate-400' : 'text-rose-400'}>{label}</span>
    </div>
);

const BOT_STATUS_CONFIG = {
    idle: { label: 'En attente', color: 'text-amber-500', icon: <PauseCircle size={14} className="text-amber-400" /> },
    scanning: { label: 'Scan en cours', color: 'text-blue-400', icon: <Activity size={14} className="text-blue-400 animate-pulse" /> },
    scanning_url: { label: 'Analyse URL', color: 'text-blue-400', icon: <Activity size={14} className="text-blue-400 animate-pulse" /> },
    cleaning: { label: 'Nettoyage', color: 'text-orange-400', icon: <Activity size={14} className="text-orange-400 animate-pulse" /> },
    reanalyzing_all: { label: 'Réanalyse', color: 'text-purple-400', icon: <Activity size={14} className="text-purple-400 animate-pulse" /> },
    paused: { label: 'En pause (12h)', color: 'text-slate-400', icon: <Power size={14} className="text-slate-400" /> },
    stopped: { label: 'Arrêté', color: 'text-rose-400', icon: <Power size={14} className="text-rose-400" /> },
};

const Navbar = ({ onOpenFilters, onOpenSettings, onClose, filterCount }) => {
    // We assume context is available since it wraps AppContent
    const botContext = useBotConfigContext();
    const { signOut } = useAuth();

    // Fallback if rendered outside context (for isolated UI tests)
    const { botStatus = 'scanning', configStatus = { status: 'success' }, isRefreshing = false, isCleaning = false, handleManualRefresh = () => { }, handleManualCleanup = () => { } } = botContext || {};

    const statusInfo = BOT_STATUS_CONFIG[botStatus] || { label: botStatus, color: 'text-slate-500', icon: <div className="w-3 h-3 rounded-full border-2 border-slate-300" /> };
    const isScanning = botStatus === 'scanning' || botStatus === 'scanning_url';

    const handleStopScan = () => {
        triggerStopScan().catch(err => alert(`Erreur STOP_SCAN: ${err.message}`));
    };

    const handleStopBot = () => {
        if (window.confirm("⏸️ Mettre le bot en pause (12h max) ? Il sera mis en veille et reprendra automatiquement. Utilisez Start Bot pour réveiller immédiatement.")) {
            triggerStopBot().catch(err => alert(`Erreur: ${err.message}`));
        }
    };

    const handleStartBot = () => {
        triggerStartBot().catch(err => alert(`Erreur START_BOT: ${err.message}`));
    };

    return (
        <nav className="sticky top-0 z-30 w-full bg-slate-900/80 backdrop-blur-lg border-b border-slate-800">
            <div className="w-full max-w-7xl mx-auto px-2 sm:px-4 h-16 flex items-center justify-between gap-2 sm:gap-4">

                {/* Logo */}
                <div className="flex items-center gap-3 shrink-0">
                    <div className="bg-blue-600 p-2 rounded-xl text-white shadow-md shadow-blue-500/20">
                        <Guitar size={20} />
                    </div>
                    <div>
                        <h1 className="text-sm sm:text-base font-black tracking-tight text-white leading-none">
                            GUITAR HUNTER <span className="text-blue-400">AI</span>
                        </h1>
                        <p className="hidden sm:block text-[9px] font-bold text-slate-500 uppercase tracking-widest leading-none">
                            Scraper & Gemini Evaluator
                        </p>
                    </div>
                </div>

                {/* Center: Interactive system controls */}
                <div className="flex items-center gap-2 lg:gap-4 flex-1 justify-center">
                    <div className="hidden lg:flex items-center gap-4">
                        <StatusDot ok={configStatus.status === 'success'} label="Auth" />
                        <div className="w-px h-4 bg-slate-800" />
                    </div>

                    {/* Bot Interactive Status */}
                    <div className="relative group flex items-center h-full flex-shrink-0">
                        <div className="flex items-center gap-1.5 text-[11px] font-bold cursor-help px-1 sm:px-2 py-1 rounded-lg transition-colors hover:bg-slate-800 whitespace-nowrap">
                            {statusInfo.icon}
                            <span className={statusInfo.color}>{statusInfo.label}</span>
                        </div>

                        {/* Horizontal Hover Menu */}
                        <div className="absolute top-full left-1/2 -translate-x-1/2 pt-2 opacity-0 group-hover:opacity-100 transition-all pointer-events-none group-hover:pointer-events-auto z-50">
                            <div className="flex flex-row items-center gap-1.5 bg-slate-800 border border-slate-700 p-1.5 rounded-xl shadow-xl">

                                {/* Scanner maintenant */}
                                <button
                                    onClick={handleManualRefresh}
                                    disabled={isRefreshing}
                                    className={`p-2 rounded-lg transition-all border ${isRefreshing ? 'bg-slate-900 border-slate-800 text-slate-500' : 'bg-slate-900 border-slate-700 text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/30'}`}
                                    title="Scanner maintenant"
                                >
                                    <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
                                </button>

                                {/* Vérifier Stocks */}
                                <button
                                    onClick={handleManualCleanup}
                                    disabled={isCleaning}
                                    className={`p-2 rounded-lg transition-all border ${isCleaning ? 'bg-slate-900 border-slate-800 text-slate-500' : 'bg-slate-900 border-slate-700 text-amber-500 hover:bg-amber-500/10 hover:border-amber-500/30'}`}
                                    title="Vérifier Stocks"
                                >
                                    <Trash2 size={16} className={isCleaning ? "animate-bounce" : ""} />
                                </button>

                                <div className="w-px h-6 bg-slate-700 mx-0.5" />

                                {/* System Control */}
                                {isScanning && (
                                    <button
                                        onClick={handleStopScan}
                                        className="p-2 rounded-lg bg-slate-900 border border-slate-700 text-orange-400 hover:bg-orange-500/10 hover:border-orange-500/30 transition-colors"
                                        title="Interrompre le scan en cours"
                                    >
                                        <Square size={16} fill="currentColor" />
                                    </button>
                                )}
                                {botStatus === 'paused' && (
                                    <button
                                        onClick={handleStartBot}
                                        className="p-2 rounded-lg bg-slate-900 border border-slate-700 text-emerald-400 hover:bg-emerald-500/10 hover:border-emerald-500/30 transition-colors"
                                        title="Réveiller le bot immédiatement"
                                    >
                                        <SkipForward size={16} fill="currentColor" />
                                    </button>
                                )}
                                {botStatus !== 'paused' && botStatus !== 'stopped' && configStatus.status === 'success' && !isScanning && (
                                    <button
                                        onClick={handleStopBot}
                                        className="p-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-400 hover:text-orange-400 hover:bg-orange-500/10 hover:border-orange-500/30 transition-colors"
                                        title="Mettre le bot en pause 12h"
                                    >
                                        <Power size={16} />
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>

                    <div className="hidden lg:flex items-center gap-4">
                        <div className="w-px h-4 bg-slate-800" />
                        <StatusDot ok={true} label="DB Connectée" />
                    </div>
                </div>

                {/* Right: Manual Actions + Filters + Settings + exit */}
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

                    {/* Paramètres button (gear icon) */}
                    <button
                        onClick={onOpenSettings}
                        className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-all"
                        title="Paramètres"
                    >
                        <Settings size={16} />
                    </button>

                    {/* Déconnexion button */}
                    <button
                        onClick={signOut}
                        className="w-9 h-9 flex items-center justify-center rounded-xl bg-slate-800 border border-slate-700 text-slate-400 hover:text-rose-500 hover:bg-rose-500/10 transition-all"
                        title="Se déconnecter"
                    >
                        <LogOut size={16} />
                    </button>
                </div>
            </div>
        </nav>
    );
};

export default Navbar;
