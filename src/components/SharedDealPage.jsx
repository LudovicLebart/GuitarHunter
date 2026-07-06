import React, { useEffect, useState } from 'react';
import { ExternalLink, MapPin, Guitar } from 'lucide-react';
import { getSharedDeal } from '../services/firestoreService';
import ImageGallery from './ImageGallery';
import VerdictBadge from './VerdictBadge';

const SCORE_LABELS = {
    price_score: 'Prix',
    condition_score: 'État',
    rareness_score: 'Rareté',
    demand_score: 'Demande',
    margin_score: 'Marge',
};

const SharedDealPage = ({ shareId }) => {
    const [deal, setDeal] = useState(null);
    const [loading, setLoading] = useState(true);
    const [notFound, setNotFound] = useState(false);

    useEffect(() => {
        if (!shareId) { setNotFound(true); setLoading(false); return; }
        getSharedDeal(shareId)
            .then(data => {
                if (!data) setNotFound(true);
                else setDeal(data);
            })
            .catch(() => setNotFound(true))
            .finally(() => setLoading(false));
    }, [shareId]);

    if (loading) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center">
                <div className="text-slate-400 text-sm">Chargement de l'annonce...</div>
            </div>
        );
    }

    if (notFound) {
        return (
            <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center gap-4 px-6 text-center">
                <Guitar size={48} className="text-slate-600" />
                <p className="text-white font-bold text-lg">Annonce introuvable</p>
                <p className="text-slate-400 text-sm">Ce lien est invalide ou a expiré.</p>
                <a href="/" className="mt-4 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-xl transition-colors">
                    Ouvrir Guitar Hunter AI
                </a>
            </div>
        );
    }

    const images = deal.storageImageUrls?.length ? deal.storageImageUrls : (deal.imageUrls || []);
    const scores = deal.scores || {};
    const scoreEntries = Object.entries(SCORE_LABELS).filter(([k]) => scores[k] != null);

    return (
        <div className="min-h-screen bg-slate-950 text-white">
            {/* Header */}
            <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center gap-3">
                <Guitar size={22} className="text-blue-400 shrink-0" />
                <span className="font-black text-sm text-white tracking-tight">Guitar Hunter <span className="text-blue-400">AI</span></span>
                <span className="ml-auto text-xs text-slate-500">Annonce partagée</span>
            </div>

            <div className="max-w-2xl mx-auto px-4 py-6 flex flex-col gap-5">
                {/* Images */}
                {images.length > 0 && (
                    <div className="rounded-2xl overflow-hidden bg-slate-900">
                        <ImageGallery images={images} title={deal.title} />
                    </div>
                )}

                {/* Title / Price / Location */}
                <div className="flex flex-col gap-2">
                    <div className="flex items-start justify-between gap-3">
                        <h1 className="text-lg font-black leading-snug">{deal.title || 'Sans titre'}</h1>
                        {deal.verdict && <VerdictBadge verdict={deal.verdict} />}
                    </div>
                    <div className="flex items-center gap-4 text-sm">
                        {deal.price != null && (
                            <span className="text-2xl font-black text-white">{deal.price} €</span>
                        )}
                        {deal.location && (
                            <span className="flex items-center gap-1 text-slate-400">
                                <MapPin size={14} /> {deal.location}
                            </span>
                        )}
                    </div>
                </div>

                {/* Scores IA */}
                {scoreEntries.length > 0 && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-3">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Scores IA</p>
                        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                            {scoreEntries.map(([key, label]) => (
                                <div key={key} className="flex flex-col gap-1">
                                    <span className="text-xs text-slate-500">{label}</span>
                                    <div className="flex items-center gap-2">
                                        <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                                            <div
                                                className="h-full bg-blue-500 rounded-full"
                                                style={{ width: `${Math.min(100, (scores[key] / 10) * 100)}%` }}
                                            />
                                        </div>
                                        <span className="text-xs font-bold text-white w-6 text-right">{scores[key]}</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Analyse IA */}
                {(deal.tier3_summary || deal.analysis) && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-2">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Analyse IA</p>
                        <p className="text-sm text-slate-300 leading-relaxed whitespace-pre-wrap">
                            {deal.tier3_summary || deal.analysis}
                        </p>
                    </div>
                )}

                {/* Description */}
                {deal.description && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-2">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Description</p>
                        <p className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap line-clamp-6">
                            {deal.description}
                        </p>
                    </div>
                )}

                {/* CTA */}
                <div className="flex flex-col sm:flex-row gap-3 pt-2">
                    {deal.link && (
                        <a
                            href={deal.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center justify-center gap-2 px-5 py-3 bg-blue-600 hover:bg-blue-500 text-white text-sm font-bold rounded-xl transition-colors"
                        >
                            <ExternalLink size={16} /> Voir l'annonce originale
                        </a>
                    )}
                    <a
                        href={`${window.location.origin}${window.location.pathname}`}
                        className="flex items-center justify-center gap-2 px-5 py-3 bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-bold rounded-xl transition-colors"
                    >
                        <Guitar size={16} /> Essayer Guitar Hunter AI
                    </a>
                </div>
            </div>
        </div>
    );
};

export default SharedDealPage;
