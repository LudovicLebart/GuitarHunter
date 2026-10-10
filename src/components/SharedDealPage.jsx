import React, { useEffect, useState } from 'react';
import { ExternalLink, MapPin, Guitar } from 'lucide-react';
import { getSharedDeal } from '../services/apiService';
import ImageGallery from './ImageGallery';
import VerdictBadge from './VerdictBadge';
import ReasoningText from './DealCard/ReasoningText';

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
    const ai = deal.aiAnalysis || {};
    const reasoning = ai.analysis || ai.reasoning || deal.analysis || null;
    const summary = ai.summary || deal.tier3_summary || null;
    const estValue = ai.estimated_value ?? ai.estimated_guitar_value ?? null;
    const computedMargin = (estValue != null && deal.price != null) ? Math.round(estValue - deal.price) : null;
    const margin = ai.estimated_gross_margin !== undefined ? ai.estimated_gross_margin : computedMargin;
    const dealScore = ai.deal_score ?? null;
    const confidence = dealScore != null ? dealScore * 10 : null;
    const specs = [
        { label: 'Marque', value: ai.brand },
        { label: 'Modèle', value: ai.model_name },
        { label: 'Année', value: ai.production_year },
        { label: 'Pays', value: ai.country_of_origin },
        { label: 'Couleur', value: ai.color },
        { label: 'Finition', value: ai.finish_application },
        { label: 'Brillance', value: ai.finish_texture },
        { label: 'Longueur manche', value: ai.neck_scale_length },
    ].filter(spec => spec.value && !/^inconnu(e)?$/i.test(String(spec.value).trim()));

    return (
        <div className="min-h-screen bg-slate-950 text-white">
            {/* Header */}
            <div className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center gap-3">
                <Guitar size={22} className="text-blue-400 shrink-0" />
                <span className="font-black text-sm text-white tracking-tight">Guitar Hunter <span className="text-blue-400">AI</span></span>
                <span className="ml-auto text-xs text-slate-500">Rapport d'expertise partagé</span>
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
                            <span className="text-2xl font-black text-white">{deal.price}$</span>
                        )}
                        {estValue != null && (
                            <span className="text-sm text-slate-400">Val. est. <span className="line-through">{estValue}$</span></span>
                        )}
                        {margin != null && (
                            <span className={`text-sm font-black ${margin > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                Marge {margin > 0 ? '+' : ''}{margin}$
                            </span>
                        )}
                        {confidence != null && (
                            <span className="text-sm text-slate-400">Confiance IA <span className="font-black text-blue-400">{Math.round(confidence)}%</span></span>
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

                {/* Résumé + fiche technique */}
                {(summary || specs.length > 0) && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-3">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Analyse IA</p>
                        {summary && (
                            <p className="text-sm text-slate-200 leading-relaxed whitespace-pre-wrap">{summary}</p>
                        )}
                        {specs.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                                {specs.map(spec => (
                                    <div key={spec.label} className="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5">
                                        <span className="text-[10px] text-slate-500 font-bold uppercase mr-1.5">{spec.label} :</span>
                                        <span className="text-xs text-slate-200 font-semibold">{spec.value}</span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* Analyse détaillée complète */}
                {reasoning && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-2">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Analyse détaillée</p>
                        <ReasoningText text={reasoning} />
                    </div>
                )}

                {/* Description */}
                {deal.description && (
                    <div className="bg-slate-900 rounded-2xl p-4 flex flex-col gap-2">
                        <p className="text-xs font-black uppercase tracking-widest text-slate-500">Description</p>
                        <p className="text-sm text-slate-400 leading-relaxed whitespace-pre-wrap">
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
                </div>
            </div>
        </div>
    );
};

export default SharedDealPage;
