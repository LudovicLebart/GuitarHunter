import React from 'react';
import { Square, Power, SkipForward, Activity, PauseCircle } from 'lucide-react';
import { useBotConfigContext } from '../context/BotConfigContext';
import { triggerStopScan, triggerStopBot, triggerStartBot } from '../services/firestoreService';

const BOT_STATUS_CONFIG = {
    idle: { label: 'En attente', color: 'text-yellow-600', icon: <PauseCircle size={12} className="text-yellow-500" /> },
    scanning: { label: 'Scan en cours', color: 'text-blue-600', icon: <Activity size={12} className="text-blue-500 animate-pulse" /> },
    scanning_url: { label: 'Analyse URL', color: 'text-blue-600', icon: <Activity size={12} className="text-blue-500 animate-pulse" /> },
    cleaning: { label: 'Nettoyage', color: 'text-orange-600', icon: <Activity size={12} className="text-orange-500 animate-pulse" /> },
    reanalyzing_all: { label: 'Réanalyse', color: 'text-purple-600', icon: <Activity size={12} className="text-purple-500 animate-pulse" /> },
    paused: { label: 'En pause (12h)', color: 'text-slate-500', icon: <Power size={12} className="text-slate-400" /> },
    stopped: { label: 'Arrêté', color: 'text-rose-600', icon: <Power size={12} className="text-rose-500" /> },
};

const BotControls = () => {
    const { botStatus, configStatus } = useBotConfigContext();

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
        <div className="flex items-start gap-2 text-[10px] font-mono mb-2 p-2 bg-slate-50 rounded-lg border border-slate-100 group">
            <div className="mt-0.5">
                {statusInfo.icon}
            </div>
            <div className="flex-1">
                <div className="font-bold uppercase text-slate-600">Engine / Bot</div>
                {configStatus.status === 'success' ? (
                    <p className={`${statusInfo.color} leading-tight mt-0.5 capitalize`}>{statusInfo.label}</p>
                ) : (
                    <p className="text-slate-400 leading-tight mt-0.5">Appairage en cours...</p>
                )}
            </div>

            {/* Contrôles interactifs affichés au hover */}
            <div className="flex items-center gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                {isScanning && (
                    <button
                        onClick={handleStopScan}
                        className="p-1.5 rounded bg-white border border-slate-200 text-orange-500 hover:bg-orange-50 hover:border-orange-200 transition-colors shadow-sm"
                        title="Interrompre le scan en cours"
                    >
                        <Square size={12} fill="currentColor" />
                    </button>
                )}

                {botStatus === 'paused' && (
                    <button
                        onClick={handleStartBot}
                        className="p-1.5 rounded bg-white border border-slate-200 text-emerald-500 hover:bg-emerald-50 hover:border-emerald-200 transition-colors shadow-sm"
                        title="Réveiller le bot immédiatement"
                    >
                        <SkipForward size={12} fill="currentColor" />
                    </button>
                )}

                {botStatus !== 'paused' && botStatus !== 'stopped' && configStatus.status === 'success' && (
                    <button
                        onClick={handleStopBot}
                        className="p-1.5 rounded bg-white border border-slate-200 text-slate-400 hover:text-orange-500 hover:bg-orange-50 hover:border-orange-200 transition-colors shadow-sm"
                        title="Mettre le bot en pause 12h"
                    >
                        <Power size={12} />
                    </button>
                )}
            </div>
        </div>
    );
};

export default BotControls;
