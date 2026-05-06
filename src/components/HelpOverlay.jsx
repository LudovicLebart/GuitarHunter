import React from 'react';
import { X, HelpCircle, Target, Zap, Bot, Mail, Bell, ShieldCheck, Info, ChevronRight, RefreshCw, Trash2, Globe, Rocket, Filter, Settings, Search, AlertCircle, MapPin, BrainCircuit } from 'lucide-react';

const HelpOverlay = ({ onClose }) => {
    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 md:p-10">
            {/* Backdrop with extreme blur */}
            <div 
                className="absolute inset-0 bg-slate-950/80 backdrop-blur-2xl animate-in fade-in duration-500" 
                onClick={onClose} 
            />

            {/* Modal Container */}
            <div className="relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-800 rounded-[2.5rem] shadow-[0_30px_100px_-20px_rgba(0,0,0,0.9)] overflow-hidden flex flex-col animate-in zoom-in-95 slide-in-from-bottom-10 duration-500">
                
                {/* Header */}
                <div className="sticky top-0 z-10 px-8 py-6 flex items-center justify-between bg-slate-900/50 backdrop-blur-md border-b border-slate-800">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-2xl bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
                            <HelpCircle size={28} />
                        </div>
                        <div>
                            <h2 className="text-xl font-black tracking-tight text-white uppercase">Guide de l'Expert</h2>
                            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Maîtrisez Guitar Hunter AI</p>
                        </div>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-3 rounded-2xl bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition-all group"
                    >
                        <X size={20} className="group-hover:rotate-90 transition-transform duration-300" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8 space-y-16 scrollbar-dark">
                    
                    {/* Section: Prise en Main */}
                    <section className="relative overflow-hidden bg-slate-950/40 border border-blue-500/10 rounded-[2.5rem] p-8">
                        <div className="absolute top-0 right-0 p-8 opacity-10">
                            <Rocket size={120} className="text-blue-500" />
                        </div>
                        <div className="relative z-10">
                            <div className="flex items-center gap-3 mb-8">
                                <Rocket className="text-blue-400" size={24} />
                                <h3 className="text-lg font-bold text-white uppercase tracking-tight">Guide de Prise en Main</h3>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                                {/* Step 1: Zones */}
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center text-[10px] font-black border border-blue-500/20">1</div>
                                        <h4 className="text-xs font-black text-white uppercase">Cibles (Villes & Rayon)</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-500 leading-relaxed">
                                        Ajoutez vos villes de recherche. <br/>
                                        <strong>RÉGLAGE CRUCIAL :</strong> Utilisez un <strong>Rayon de 0 km</strong> pour un scan STRICT sur la ville uniquement. Cela évite d'être noyé par les annonces des communes voisines.
                                    </p>
                                </div>
                                
                                {/* Step 2: Vigilance */}
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-lg bg-emerald-600/20 text-emerald-400 flex items-center justify-center text-[10px] font-black border border-emerald-500/20">2</div>
                                        <h4 className="text-xs font-black text-white uppercase">Vigilance (Fréquence & Volume)</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-500 leading-relaxed">
                                        Réglez la <strong>Fréquence</strong> (repos du bot, conseillé 60 min) et le <strong>Max Annonces</strong> (items scannés par ville, conseillé 20-30). Des réglages trop agressifs peuvent mener à un blocage Facebook.
                                    </p>
                                </div>

                                {/* Step 3: Scan */}
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-lg bg-purple-600/20 text-purple-400 flex items-center justify-center text-[10px] font-black border border-purple-500/20">3</div>
                                        <h4 className="text-xs font-black text-white uppercase">Lancez le Scan</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-500 leading-relaxed">
                                        Utilisez le bouton <strong>"Lancer le Scan"</strong> directement dans le panneau des paramètres pour peupler votre base de données immédiatement.
                                    </p>
                                </div>

                                {/* Step 4: Analyse */}
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-6 h-6 rounded-lg bg-amber-600/20 text-amber-400 flex items-center justify-center text-[10px] font-black border border-amber-500/20">4</div>
                                        <h4 className="text-xs font-black text-white uppercase">Identifiez les Pépites</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-500 leading-relaxed">
                                        Consultez les scores de l'IA (Deal, État, Authenticité). Les opportunités exceptionnelles sont marquées du verdict <strong>PÉPITE</strong>.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </section>
                    
                    {/* Section: Le Radar IA */}
                    <section>
                        <div className="flex items-center gap-3 mb-6">
                            <Target className="text-emerald-400" size={24} />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Le Radar IA (Gemini)</h3>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="bg-slate-800/50 p-5 rounded-3xl border border-slate-700/50">
                                <h4 className="text-sm font-black text-emerald-400 uppercase mb-2">Comment ça marche ?</h4>
                                <p className="text-sm text-slate-400 leading-relaxed">
                                    Chaque annonce est "scannée" par les modèles Google Gemini. Ils extraient les métadonnées et analysent les photos pour confirmer le modèle, l'état et l'authenticité.
                                </p>
                            </div>
                            <div className="bg-slate-800/50 p-5 rounded-3xl border border-slate-700/50">
                                <h4 className="text-sm font-black text-emerald-400 uppercase mb-2">Les 5 Scores</h4>
                                <ul className="text-sm text-slate-400 space-y-2">
                                    <li className="flex items-start gap-2"><div className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" /> <span><strong>Deal :</strong> Rentabilité immédiate (ROI).</span></li>
                                    <li className="flex items-start gap-2"><div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-1.5 shrink-0" /> <span><strong>Authenticité :</strong> Risque de contrefaçon ou "partscaster".</span></li>
                                    <li className="flex items-start gap-2"><div className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" /> <span><span><strong>État :</strong> Cosmétique et structurel.</span></span></li>
                                    <li className="flex items-start gap-2"><div className="w-1.5 h-1.5 rounded-full bg-purple-500 mt-1.5 shrink-0" /> <span><strong>Liquidité :</strong> Vitesse de revente estimée.</span></li>
                                </ul>
                            </div>
                        </div>
                    </section>

                    {/* Section: Les Verdicts */}
                    <section>
                        <div className="flex items-center gap-3 mb-6">
                            <Zap className="text-blue-400" size={24} />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Les Verdicts de l'Expert</h3>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                            {[
                                { id: 'PEPITE', label: 'PÉPITE', color: 'bg-emerald-500', desc: 'ROI exceptionnel, achat immédiat recommandé.' },
                                { id: 'FAST_FLIP', label: 'FAST FLIP', color: 'bg-blue-500', desc: 'Revente rapide avec profit modéré.' },
                                { id: 'LUTHIER', label: 'PROJET', color: 'bg-orange-500', desc: 'Nécessite des réparations mais gros potentiel.' },
                                { id: 'COLLECTION', label: 'COLLECTION', color: 'bg-purple-500', desc: 'Pièce rare, valeur stable ou croissante.' },
                                { id: 'CASE_WIN', label: 'CASE WIN', color: 'bg-indigo-500', desc: 'L\'accessoire (étui, pédale) vaut le détour.' },
                                { id: 'BAD_DEAL', label: 'À ÉVITER', color: 'bg-rose-500', desc: 'Trop cher ou trop de risques détectés.' },
                            ].map(v => (
                                <div key={v.id} className="p-4 bg-slate-800/30 border border-slate-800 rounded-2xl hover:bg-slate-800/50 transition-colors">
                                    <div className="flex items-center gap-2 mb-2">
                                        <div className={`w-2 h-2 rounded-full ${v.color}`} />
                                        <span className="text-xs font-black text-white">{v.label}</span>
                                    </div>
                                    <p className="text-[11px] text-slate-500 leading-tight">{v.desc}</p>
                                </div>
                            ))}
                        </div>
                    </section>

                    {/* Section: Commandes & Contrôle */}
                    <section>
                        <div className="flex items-center gap-3 mb-6">
                            <Bot className="text-purple-400" size={24} />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Commandes du Bot</h3>
                        </div>
                        <div className="space-y-4">
                            <div className="flex items-center gap-6 p-6 bg-slate-950/50 border border-slate-800 rounded-[2rem]">
                                <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl text-emerald-400 shadow-xl shadow-emerald-500/5">
                                    <RefreshCw size={24} />
                                </div>
                                <div className="flex-1">
                                    <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-wider">Scanner maintenant (Refresh)</h4>
                                    <p className="text-xs text-slate-500 leading-relaxed">
                                        Force le bot à scanner immédiatement Facebook Marketplace. Le bot cherchera de nouvelles annonces selon vos villes configurées.
                                    </p>
                                </div>
                            </div>
                            
                            <div className="flex items-center gap-6 p-6 bg-slate-950/50 border border-slate-800 rounded-[2rem]">
                                <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl text-amber-400 shadow-xl shadow-amber-500/5">
                                    <Trash2 size={24} />
                                </div>
                                <div className="flex-1">
                                    <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-wider">Nettoyage (Cleanup)</h4>
                                    <p className="text-xs text-slate-500 leading-relaxed">
                                        Le bot visite chaque annonce en base pour vérifier si elle est toujours en ligne. Les annonces vendues ou supprimées sont marquées comme telles.
                                    </p>
                                </div>
                            </div>

                            <div className="flex items-center gap-6 p-6 bg-slate-950/50 border border-slate-800 rounded-[2rem]">
                                <div className="p-4 bg-slate-900 border border-slate-800 rounded-2xl text-blue-400 shadow-xl shadow-blue-500/5">
                                    <Globe size={24} />
                                </div>
                                <div className="flex-1">
                                    <h4 className="text-sm font-bold text-white mb-1 uppercase tracking-wider">Scan URL Spécifique</h4>
                                    <p className="text-xs text-slate-500 leading-relaxed">
                                        Dans les paramètres, vous pouvez coller une URL Marketplace. Le bot l'analysera immédiatement, même si elle est hors de vos zones habituelles.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </section>
                    
                    {/* Section: Filtres & Paramètres */}
                    <section>
                        <div className="flex items-center gap-3 mb-8">
                            <Settings className="text-amber-400" size={24} />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Configuration Experte</h3>
                        </div>
                        <div className="bg-slate-900/50 border border-slate-800 rounded-[2.5rem] overflow-hidden">
                            <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-slate-800">
                                {/* Parameter: Rayon */}
                                <div className="p-8 space-y-4">
                                    <div className="flex items-center gap-2 text-blue-400">
                                        <MapPin size={18} />
                                        <h4 className="text-xs font-black uppercase tracking-widest">Rayon (Distance)</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-400 leading-relaxed">
                                        Définit l'étendue du scan autour de vos villes.
                                    </p>
                                    <div className="p-4 bg-blue-500/5 border border-blue-500/20 rounded-2xl">
                                        <p className="text-[10px] font-bold text-blue-400 uppercase mb-2">💡 Le Secret du Rayon 0</p>
                                        <p className="text-[10px] text-slate-300 leading-relaxed italic">
                                            "Un rayon de <strong>0 km</strong> active la recherche <strong>STRICTE</strong>. Facebook ne renverra que les objets situés précisément dans la ville nommée, sans aucun débordement sur les zones voisines."
                                        </p>
                                    </div>
                                </div>

                                {/* Parameter: Fréquence */}
                                <div className="p-8 space-y-4">
                                    <div className="flex items-center gap-2 text-emerald-400">
                                        <RefreshCw size={18} />
                                        <h4 className="text-xs font-black uppercase tracking-widest">Fréquence (min)</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-400 leading-relaxed">
                                        Le temps de repos du bot entre deux scans.
                                    </p>
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between text-[10px]">
                                            <span className="text-slate-500 uppercase font-bold">Recommandé</span>
                                            <span className="text-emerald-400 font-bold">60 min</span>
                                        </div>
                                        <p className="text-[10px] text-slate-500 leading-relaxed">
                                            Trop bas (ex: 5 min) peut entraîner un blocage temporaire par Facebook. Restez au-dessus de 30 min pour une sécurité optimale.
                                        </p>
                                    </div>
                                </div>

                                {/* Parameter: Max Annonces */}
                                <div className="p-8 space-y-4">
                                    <div className="flex items-center gap-2 text-purple-400">
                                        <Search size={18} />
                                        <h4 className="text-xs font-black uppercase tracking-widest">Max Annonces</h4>
                                    </div>
                                    <p className="text-[11px] text-slate-400 leading-relaxed">
                                        Volume d'items analysés par cycle et par ville.
                                    </p>
                                    <div className="space-y-2">
                                        <p className="text-[10px] text-slate-500 leading-relaxed">
                                            Si réglé sur <strong>20</strong>, le bot examine les 20 premières annonces du Marketplace pour chaque ville.
                                        </p>
                                        <p className="text-[10px] text-slate-500 leading-relaxed italic border-l border-slate-800 pl-3">
                                            Augmentez ce chiffre si vous cherchez dans des mégalopoles très actives.
                                        </p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Section: Alertes */}
                    <section>
                        <div className="flex items-center gap-3 mb-6">
                            <Bell className="text-orange-400" size={24} />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Système d'Alertes</h3>
                        </div>
                        <div className="bg-gradient-to-br from-slate-800/50 to-slate-900/50 p-8 rounded-[2.5rem] border border-slate-800 shadow-2xl">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-center">
                                <div>
                                    <div className="flex items-center gap-2 mb-4 bg-orange-500/10 w-fit px-3 py-1 rounded-full border border-orange-500/20">
                                        <Mail size={14} className="text-orange-400" />
                                        <span className="text-[10px] font-black text-orange-400 uppercase tracking-widest">Notification Directe</span>
                                    </div>
                                    <h4 className="text-2xl font-black text-white mb-4 leading-tight">Notifications par Email</h4>
                                    <p className="text-sm text-slate-400 leading-relaxed mb-6">
                                        Dès qu'une <strong>PÉPITE</strong> est détectée ou qu'une baisse de prix majeure survient, vous recevez un email automatique. Plus besoin de surveiller l'écran 24h/24.
                                    </p>
                                    <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                                        <ShieldCheck size={16} className="text-emerald-500" />
                                        <span>Utilise votre email de connexion Firebase</span>
                                    </div>
                                </div>
                                <div className="bg-slate-900/40 p-6 rounded-3xl border border-slate-800">
                                    <h5 className="text-xs font-black text-slate-300 uppercase mb-3">Critères d'Alerte</h5>
                                    <ul className="text-[11px] text-slate-500 space-y-2">
                                        <li className="flex items-center gap-2"><div className="w-1 h-1 rounded-full bg-orange-500" /> Verdict classé en "PÉPITE"</li>
                                        <li className="flex items-center gap-2"><div className="w-1 h-1 rounded-full bg-orange-500" /> Baisse de prix détectée sur un item suivi</li>
                                        <li className="flex items-center gap-2"><div className="w-1 h-1 rounded-full bg-orange-500" /> Alerte personnalisée (via topic ntfy optionnel)</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </section>

                    {/* Section: Expertise IA (Advanced) */}
                    <section className="bg-purple-500/5 border border-purple-500/10 rounded-[2.5rem] p-8">
                        <div className="flex items-center gap-3 mb-6">
                            <BrainCircuit size={24} className="text-purple-400" />
                            <h3 className="text-lg font-bold text-white uppercase tracking-tight">Expertise Avancée (IA)</h3>
                        </div>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="bg-slate-800/30 p-6 rounded-3xl border border-slate-800">
                                <h4 className="text-xs font-black text-purple-400 uppercase mb-3 tracking-widest">Intelligence & Prompts</h4>
                                <p className="text-[11px] text-slate-400 leading-relaxed">
                                    Vous pouvez modifier les <strong>Prompts</strong> d'analyse pour ajuster la sévérité du Portier, demander à l'IA de surveiller des marques spécifiques ou changer le ton des rapports d'expertise.
                                </p>
                            </div>
                            <div className="bg-slate-800/30 p-6 rounded-3xl border border-slate-800">
                                <h4 className="text-xs font-black text-purple-400 uppercase mb-3 tracking-widest">Re-Analyse Globale</h4>
                                <p className="text-[11px] text-slate-400 leading-relaxed">
                                    Le bouton "Relancer Analyses" permet de soumettre à nouveau toute votre base de données aux derniers Prompts configurés, utile après un changement majeur de stratégie.
                                </p>
                            </div>
                        </div>
                    </section>

                </div>

                {/* Footer */}
                <div className="px-8 py-6 bg-slate-950 border-t border-slate-800 flex items-center justify-between">
                    <p className="text-[10px] font-bold text-slate-600 uppercase tracking-[0.2em]">
                        Guitar Hunter AI v3.0 — Gemini Optimized
                    </p>
                    <button 
                        onClick={onClose}
                        className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-black uppercase tracking-widest rounded-xl transition-all shadow-lg shadow-blue-600/20 active:scale-95"
                    >
                        Compris !
                    </button>
                </div>
            </div>
        </div>
    );
};

export default HelpOverlay;
