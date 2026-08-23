import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, AlertTriangle, ArrowLeft, Paperclip, X, Camera, Image as ImageIcon, ImagePlus, Check, Wrench, ArrowUpDown } from 'lucide-react';
import { useDealChat, getAttachedImagePartIndices, getAddedToGalleryUrl, getRestorationProposalState } from '../../hooks/useDealChat';
import { useAuth } from '../../hooks/useAuth';
import { useBotConfigContext } from '../../context/BotConfigContext';
import { RESTORATION_CATEGORY_LABELS } from '../../constants/restorationPlan';
import { resolveRestorationReorderProposal } from '../../services/geminiChatService';

// Carte de proposition d'étape de restauration (2026-08-22, Lot B ; réordonnancement 2026-08-23)
// — sous une bulle modèle portant `restorationProposals`. Jamais d'écriture silencieuse :
// Appliquer/Ignorer explicites, état persisté sur le message (`getRestorationProposalState`) pour
// ne jamais se réactiver après un reload — `busy` reste local (spinner pendant l'écriture, comme
// `galleryUploadState`). `liveItems` (le plan RÉEL et courant, pas un instantané du tour de chat)
// est nécessaire pour l'aperçu d'un réordonnancement — voir resolveRestorationReorderProposal,
// recalculé à chaque rendu pour ne jamais afficher un ordre qui ne correspond plus au plan actuel.
const RestorationProposalCard = ({ proposal, state, busy, error, liveItems, onApply, onDismiss }) => {
    const isReorder = proposal.type === 'reorder';
    const resolved = isReorder ? resolveRestorationReorderProposal(proposal.orderedItemRefs, liveItems) : null;

    return (
        <div className="mt-2 bg-slate-900/60 border border-purple-500/20 rounded-xl p-2.5">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-purple-300 uppercase tracking-wide mb-1">
                {isReorder
                    ? <><ArrowUpDown size={11} /> Proposition de réordonnancement</>
                    : <><Wrench size={11} /> Proposition d'étape · {RESTORATION_CATEGORY_LABELS[proposal.category] || proposal.category}</>}
            </div>
            {isReorder ? (
                resolved?.valid ? (
                    <ol className="text-xs text-slate-300 space-y-0.5 list-decimal list-inside">
                        {resolved.orderedItems.map(item => <li key={item.id}>{item.label}</li>)}
                    </ol>
                ) : (
                    <div className="flex items-center gap-1.5 text-xs text-amber-300">
                        <AlertTriangle size={12} className="shrink-0" /> Le plan a changé depuis cette proposition — elle n'est plus applicable.
                    </div>
                )
            ) : (
                <>
                    <div className="text-sm font-bold text-slate-100">{proposal.label}</div>
                    {proposal.estimatedCost != null && <div className="text-xs text-slate-400 mt-0.5">≈ {proposal.estimatedCost}$ estimé</div>}
                </>
            )}
            {proposal.justification && <div className="text-xs text-slate-400 mt-1 italic">{proposal.justification}</div>}
            {state?.status === 'applied' ? (
                <div className="mt-2 flex items-center gap-1.5 text-[11px] font-bold text-emerald-300">
                    <Check size={12} /> {isReorder ? 'Nouvel ordre appliqué' : 'Ajoutée au plan de restauration'}
                </div>
            ) : state?.status === 'dismissed' ? (
                <div className="mt-2 text-[11px] font-bold text-slate-500">Ignorée</div>
            ) : (
                <>
                    <div className="flex gap-2 mt-2">
                        <button
                            onClick={onDismiss}
                            disabled={busy}
                            className="px-3 py-1.5 rounded-lg text-[11px] font-bold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50"
                        >
                            Ignorer
                        </button>
                        <button
                            onClick={onApply}
                            disabled={busy || (isReorder && !resolved?.valid)}
                            className="px-3 py-1.5 rounded-lg text-[11px] font-bold text-white bg-purple-600 hover:bg-purple-500 disabled:opacity-50 transition-colors flex items-center gap-1.5"
                        >
                            {busy && <Loader2 size={11} className="animate-spin" />}
                            Appliquer
                        </button>
                    </div>
                    {error && (
                        <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-rose-300">
                            <AlertTriangle size={11} className="shrink-0" /> {error}
                        </div>
                    )}
                </>
            )}
        </div>
    );
};

// `images` : tableau de photos jointes à ce message (2026-08-22, plusieurs par message) — chaque
// entrée `{ partIndex, inlineData, addedToGalleryUrl, galleryState }`. `galleryState` : undefined
// (rien à faire) | 'uploading' | 'error' — état LOCAL à cette photo précise (pas au message ni au
// chat entier), pour que l'upload d'une photo n'affecte pas les autres. `addedToGalleryUrl` vient
// de Firestore (persisté, voir markChatMessageAddedToGallery) — source de vérité qui survit à un
// reload ou à un 2e client, contrairement à `galleryState`.
const ChatBubble = ({ role, text, images, onAddToGallery, proposals }) => {
    const isUser = role === 'user';
    return (
        <div className={`flex items-start gap-2.5 ${isUser ? 'flex-row-reverse' : ''}`}>
            <div className={`w-7 h-7 shrink-0 rounded-full flex items-center justify-center ${isUser ? 'bg-blue-600' : 'bg-purple-600'}`}>
                {isUser ? <User size={14} className="text-white" /> : <Bot size={14} className="text-white" />}
            </div>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${isUser
                ? 'bg-blue-600 text-white rounded-tr-sm'
                : 'bg-slate-800 text-slate-200 rounded-tl-sm'
                }`}>
                {images?.length > 0 && (
                    <div className={`grid gap-1.5 ${images.length > 1 ? 'grid-cols-2' : ''} ${text ? 'mb-2' : ''}`}>
                        {images.map(({ partIndex, inlineData, addedToGalleryUrl, galleryState }) => (
                            <div key={partIndex}>
                                <img
                                    src={`data:${inlineData.mimeType};base64,${inlineData.data}`}
                                    alt="Photo jointe"
                                    className="rounded-lg w-full max-h-56 object-contain"
                                />
                                <button
                                    onClick={() => onAddToGallery(partIndex)}
                                    disabled={!!addedToGalleryUrl || galleryState === 'uploading'}
                                    className={`mt-1 w-full flex items-center justify-center gap-1.5 text-[11px] font-bold rounded-lg px-2.5 py-1.5 transition-colors ${addedToGalleryUrl
                                        ? 'bg-emerald-500/15 text-emerald-300 cursor-default'
                                        : galleryState === 'error'
                                            ? 'bg-rose-500/15 text-rose-300 hover:bg-rose-500/25'
                                            : 'bg-white/10 text-white/80 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed'
                                        }`}
                                >
                                    {galleryState === 'uploading' ? (
                                        <><Loader2 size={12} className="animate-spin" /> Ajout en cours...</>
                                    ) : addedToGalleryUrl ? (
                                        <><Check size={12} /> Ajoutée à la galerie</>
                                    ) : galleryState === 'error' ? (
                                        <><AlertTriangle size={12} /> Échec — réessayer</>
                                    ) : (
                                        <><ImagePlus size={12} /> Ajouter à la galerie</>
                                    )}
                                </button>
                            </div>
                        ))}
                    </div>
                )}
                {text}
                {proposals?.map(p => (
                    <RestorationProposalCard
                        key={p.index}
                        proposal={p.proposal}
                        state={p.state}
                        busy={p.busy}
                        error={p.error}
                        liveItems={p.liveItems}
                        onApply={p.onApply}
                        onDismiss={p.onDismiss}
                    />
                ))}
            </div>
        </div>
    );
};

const DealChatPanel = ({ deal, onBack, onGalleryImageAdded, initialDraft, autoSend, onDraftConsumed, restorationItems }) => {
    const { user } = useAuth();
    const { analysisConfig } = useBotConfigContext();
    const {
        messages, loading, sending, error, sendMessage, addPhotoToGallery,
        applyRestorationProposal, dismissRestorationProposal,
    } = useDealChat(deal, user, analysisConfig?.expertModel, restorationItems);
    const [input, setInput] = useState('');
    const [imageFiles, setImageFiles] = useState([]);
    const [imagePreviews, setImagePreviews] = useState([]);
    const [showAttachMenu, setShowAttachMenu] = useState(false);
    // État LOCAL par photo (clé `${messageId}:${partIndex}` → 'uploading' | 'error'), voir
    // ChatBubble — n'affecte jamais le bandeau d'erreur global du chat (`error`, ci-dessus), qui
    // reste réservé aux échecs Gemini.
    const [galleryUploadState, setGalleryUploadState] = useState({});
    // Même principe pour les propositions de restauration (clé `${messageId}:${index}` →
    // 'applying'), voir RestorationProposalCard.
    const [proposalBusyState, setProposalBusyState] = useState({});
    // Message d'erreur par proposition (même clé) — ex. réordonnancement devenu caduc entretemps
    // (voir applyRestorationProposal). Effacé au début de chaque nouvelle tentative.
    const [proposalErrorState, setProposalErrorState] = useState({});
    const scrollRef = useRef(null);
    const cameraInputRef = useRef(null);
    const galleryInputRef = useRef(null);

    const handleAddToGallery = async (message, partIndex) => {
        const key = `${message.id}:${partIndex}`;
        if (getAddedToGalleryUrl(message, partIndex) || galleryUploadState[key] === 'uploading') return;
        setGalleryUploadState(prev => ({ ...prev, [key]: 'uploading' }));
        try {
            const url = await addPhotoToGallery(message, partIndex);
            setGalleryUploadState(prev => {
                const next = { ...prev };
                delete next[key];
                return next;
            });
            if (url) onGalleryImageAdded?.(deal.id, url);
        } catch (e) {
            console.error('Erreur ajout à la galerie:', e);
            setGalleryUploadState(prev => ({ ...prev, [key]: 'error' }));
        }
    };

    const handleApplyProposal = async (message, index) => {
        const key = `${message.id}:${index}`;
        if (getRestorationProposalState(message, index)?.status || proposalBusyState[key]) return;
        setProposalBusyState(prev => ({ ...prev, [key]: true }));
        setProposalErrorState(prev => { const next = { ...prev }; delete next[key]; return next; });
        try {
            await applyRestorationProposal(message, index);
        } catch (e) {
            console.error('Erreur application de la proposition de restauration:', e);
            setProposalErrorState(prev => ({ ...prev, [key]: e.message || "Impossible d'appliquer cette proposition." }));
        } finally {
            setProposalBusyState(prev => { const next = { ...prev }; delete next[key]; return next; });
        }
    };

    const handleDismissProposal = async (message, index) => {
        const key = `${message.id}:${index}`;
        if (getRestorationProposalState(message, index)?.status || proposalBusyState[key]) return;
        setProposalBusyState(prev => ({ ...prev, [key]: true }));
        try {
            await dismissRestorationProposal(message, index);
        } catch (e) {
            console.error('Erreur rejet de la proposition de restauration:', e);
        } finally {
            setProposalBusyState(prev => { const next = { ...prev }; delete next[key]; return next; });
        }
    };

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages, sending]);

    // Brouillon pré-rempli depuis un point d'entrée externe du plan de restauration —
    // "Demander conseil" (autoSend=false, l'utilisateur édite/envoie lui-même) ou "Faire le
    // point"/"Préparer l'annonce de revente" (autoSend=true, prompt prédéfini envoyé directement
    // sans repasser par l'état `input` pour éviter un envoi basé sur une valeur pas encore
    // committée). N'écrase jamais une saisie en cours autrement, seulement quand le parent fournit
    // un nouveau brouillon. En mode autoSend, si un envoi est déjà en cours (`sending`),
    // `sendMessage` no-op silencieusement (garde interne du hook) — on ne consomme alors PAS le
    // brouillon (pas de `onDraftConsumed()`), pour réessayer automatiquement dès que `sending`
    // repasse à false plutôt que de perdre le prompt sans aucun retour.
    useEffect(() => {
        if (!initialDraft) return;
        if (autoSend) {
            if (sending) return;
            sendMessage(initialDraft, []);
        } else {
            setInput(initialDraft);
        }
        onDraftConsumed?.();
    }, [initialDraft, autoSend, sending, onDraftConsumed, sendMessage]);

    // Révoque les URL locales de prévisualisation au démontage UNIQUEMENT (2026-08-22 — bug
    // trouvé en revue : lier ce cleanup à `[imagePreviews]` révoquait TOUT le tableau précédent à
    // chaque ajout/retrait, y compris les photos encore sélectionnées, cassant leurs miniatures ;
    // handlePickImage/clearImageAt/clearImages révoquent déjà chacun explicitement l'URL qui les
    // concerne, donc seul l'oubli au démontage doit être rattrapé ici). Le ref garde toujours la
    // dernière valeur sans re-déclencher l'effet.
    const imagePreviewsRef = useRef(imagePreviews);
    imagePreviewsRef.current = imagePreviews;
    useEffect(() => {
        return () => { imagePreviewsRef.current.forEach(URL.revokeObjectURL); };
    }, []);

    // Ajoute les photos choisies à la sélection en cours (2026-08-22, plusieurs photos par
    // message) plutôt que de remplacer la précédente. Plafonné (décodage/encodage coûteux par
    // photo, voir blobToInlinePart) pour éviter qu'une sélection massive ne sature la mémoire du
    // navigateur au moment de l'envoi.
    const MAX_ATTACHED_IMAGES = 6;
    const handlePickImage = (e) => {
        const files = Array.from(e.target.files || []);
        e.target.value = ''; // permet de resélectionner les mêmes photos à la suite
        if (!files.length) return;
        const accepted = files.slice(0, MAX_ATTACHED_IMAGES - imageFiles.length);
        if (!accepted.length) return;
        setImageFiles(prev => [...prev, ...accepted]);
        setImagePreviews(prev => [...prev, ...accepted.map(f => URL.createObjectURL(f))]);
    };

    const clearImageAt = (index) => {
        URL.revokeObjectURL(imagePreviews[index]);
        setImageFiles(prev => prev.filter((_, i) => i !== index));
        setImagePreviews(prev => prev.filter((_, i) => i !== index));
    };

    const clearImages = () => {
        imagePreviews.forEach(URL.revokeObjectURL);
        setImageFiles([]);
        setImagePreviews([]);
    };

    // Envoi déclenché UNIQUEMENT par ce bouton (2026-08-22) — jamais par la touche Entrée, pour
    // ne pas interférer avec la validation d'un caractère composé en saisie multilingue (IME :
    // chinois, japonais, coréen...), qui utilise elle aussi la touche Entrée.
    const handleSend = () => {
        if ((!input.trim() && !imageFiles.length) || sending) return;
        sendMessage(input, imageFiles);
        setInput('');
        clearImages();
    };

    return (
        <div className="flex-1 flex flex-col min-h-0">
            {/* Header */}
            <div className="flex items-center gap-2 p-4 border-b border-slate-800 shrink-0">
                <button
                    onClick={onBack}
                    className="w-8 h-8 flex items-center justify-center rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-colors shrink-0"
                    title="Retour à l'analyse"
                >
                    <ArrowLeft size={16} />
                </button>
                <div className="min-w-0">
                    <h3 className="text-sm font-black text-white truncate">Discuter avec Gemini</h3>
                    <p className="text-[11px] text-slate-500 truncate">{deal.title}</p>
                </div>
            </div>

            {/* Messages */}
            {/* max-h en filet de sécurité (2026-08-01) : garantit un plafond même si un ancêtre
                flex ne se contraint pas correctement (ex: cache navigateur/build non rechargé),
                en plus de flex-1/min-h-0 qui gèrent le cas normal. */}
            <div ref={scrollRef} className="flex-1 min-h-0 max-h-[55vh] overflow-y-auto p-4 space-y-4 scrollbar-dark">
                {loading && (
                    <div className="flex items-center justify-center h-full text-slate-500 text-sm gap-2">
                        <Loader2 size={16} className="animate-spin" /> Chargement de la conversation...
                    </div>
                )}

                {!loading && messages.length === 0 && (
                    <div className="text-center text-slate-500 text-sm py-8 px-4">
                        Pose ta première question sur cette annonce — Gemini a accès aux photos et à l'analyse déjà réalisée par Guitar Hunter AI.
                    </div>
                )}

                {messages.map(m => {
                    // Rétrocompatibilité (2026-08-22, voir getAttachedImagePartIndices/
                    // getAddedToGalleryUrl dans useDealChat.js — source unique de la conversion
                    // ancien champ singulier → nouveau champ pluriel, réutilisée par les gardes
                    // anti-double-ajout ci-dessus).
                    const images = getAttachedImagePartIndices(m)
                        .filter(partIndex => m.parts?.[partIndex]?.inlineData)
                        .map(partIndex => ({
                            partIndex,
                            inlineData: m.parts[partIndex].inlineData,
                            addedToGalleryUrl: getAddedToGalleryUrl(m, partIndex),
                            galleryState: galleryUploadState[`${m.id}:${partIndex}`],
                        }));
                    const proposals = m.restorationProposals?.map((proposal, index) => ({
                        index,
                        proposal,
                        state: getRestorationProposalState(m, index),
                        busy: !!proposalBusyState[`${m.id}:${index}`],
                        error: proposalErrorState[`${m.id}:${index}`],
                        liveItems: restorationItems,
                        onApply: () => handleApplyProposal(m, index),
                        onDismiss: () => handleDismissProposal(m, index),
                    }));
                    return (
                        <ChatBubble
                            key={m.id}
                            role={m.role}
                            text={m.displayText}
                            images={images}
                            onAddToGallery={(partIndex) => handleAddToGallery(m, partIndex)}
                            proposals={proposals}
                        />
                    );
                })}

                {sending && (
                    <div className="flex items-start gap-2.5">
                        <div className="w-7 h-7 shrink-0 rounded-full flex items-center justify-center bg-purple-600">
                            <Bot size={14} className="text-white" />
                        </div>
                        <div className="bg-slate-800 rounded-2xl rounded-tl-sm px-4 py-2.5">
                            <Loader2 size={16} className="animate-spin text-slate-400" />
                        </div>
                    </div>
                )}
            </div>

            {/* Error banner */}
            {error && (
                <div className="mx-4 mb-2 flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs rounded-xl px-3 py-2 shrink-0">
                    <AlertTriangle size={14} className="shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            {/* Input */}
            <div className="p-4 border-t border-slate-800 shrink-0">
                {imagePreviews.length > 0 && (
                    <div className="flex flex-wrap gap-2 mb-2">
                        {imagePreviews.map((url, i) => (
                            <div key={url} className="relative inline-block">
                                <img src={url} alt="Photo à envoyer" className="h-16 w-16 object-cover rounded-lg border border-slate-700" />
                                <button
                                    onClick={() => clearImageAt(i)}
                                    className="absolute -top-1.5 -right-1.5 w-5 h-5 flex items-center justify-center rounded-full bg-slate-900 border border-slate-700 text-slate-400 hover:text-white hover:bg-rose-600 hover:border-rose-600 transition-colors"
                                    title="Retirer la photo"
                                >
                                    <X size={12} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
                <div className="flex items-end gap-2">
                    {/* Deux inputs séparés plutôt qu'un seul avec/sans `capture` : sur plusieurs
                        navigateurs mobiles, `capture="environment"` force l'appareil photo (pas
                        de galerie) et son absence force la galerie (pas d'appareil photo) — aucune
                        combinaison unique ne propose fiablement les deux. Le menu ci-dessous laisse
                        l'utilisateur choisir explicitement, chaque option déclenchant le bon input. */}
                    <input
                        ref={cameraInputRef}
                        type="file"
                        accept="image/*"
                        capture="environment"
                        onChange={handlePickImage}
                        className="hidden"
                    />
                    <input
                        ref={galleryInputRef}
                        type="file"
                        accept="image/*"
                        multiple
                        onChange={handlePickImage}
                        className="hidden"
                    />

                    <div className="relative shrink-0">
                        <button
                            onClick={() => setShowAttachMenu(v => !v)}
                            disabled={loading || sending}
                            className="w-10 h-10 flex items-center justify-center rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                            title="Joindre une photo"
                        >
                            <Paperclip size={16} />
                        </button>

                        {showAttachMenu && (
                            <>
                                <div className="fixed inset-0 z-40" onClick={() => setShowAttachMenu(false)} />
                                <div className="absolute bottom-full left-0 mb-2 w-56 z-50">
                                    <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
                                        <button
                                            onClick={() => { setShowAttachMenu(false); cameraInputRef.current?.click(); }}
                                            className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                                        >
                                            <Camera size={15} /> Prendre une photo
                                        </button>
                                        <button
                                            onClick={() => { setShowAttachMenu(false); galleryInputRef.current?.click(); }}
                                            className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 transition-colors"
                                        >
                                            <ImageIcon size={15} /> Choisir depuis la galerie
                                        </button>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>

                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        disabled={loading || sending}
                        placeholder="Ta question..."
                        rows={1}
                        className="flex-1 resize-none bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500 transition-all disabled:opacity-50"
                    />
                    <button
                        onClick={handleSend}
                        disabled={loading || sending || (!input.trim() && !imageFiles.length)}
                        className="w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-purple-600 hover:bg-purple-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Envoyer"
                    >
                        <Send size={16} />
                    </button>
                </div>
            </div>
        </div>
    );
};

export default DealChatPanel;
