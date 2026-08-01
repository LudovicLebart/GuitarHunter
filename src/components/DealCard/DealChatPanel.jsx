import React, { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, AlertTriangle, ArrowLeft, Paperclip, X } from 'lucide-react';
import { useDealChat } from '../../hooks/useDealChat';
import { useAuth } from '../../hooks/useAuth';
import { useBotConfigContext } from '../../context/BotConfigContext';

const ChatBubble = ({ role, text, attachedImage }) => {
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
                {attachedImage && (
                    <img
                        src={`data:${attachedImage.mimeType};base64,${attachedImage.data}`}
                        alt="Photo jointe"
                        className={`rounded-lg max-w-full max-h-56 object-contain ${text ? 'mb-2' : ''}`}
                    />
                )}
                {text}
            </div>
        </div>
    );
};

const DealChatPanel = ({ deal, onBack }) => {
    const { user } = useAuth();
    const { analysisConfig } = useBotConfigContext();
    const { messages, loading, sending, error, sendMessage } = useDealChat(deal, user, analysisConfig?.expertModel);
    const [input, setInput] = useState('');
    const [imageFile, setImageFile] = useState(null);
    const [imagePreviewUrl, setImagePreviewUrl] = useState(null);
    const scrollRef = useRef(null);
    const fileInputRef = useRef(null);

    useEffect(() => {
        scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }, [messages, sending]);

    // Révoque l'URL locale de prévisualisation dès qu'elle n'est plus utilisée (changement de
    // photo ou démontage), pour ne pas fuiter de mémoire (object URL jamais libérée sinon).
    useEffect(() => {
        return () => { if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl); };
    }, [imagePreviewUrl]);

    const handlePickImage = (e) => {
        const file = e.target.files?.[0];
        e.target.value = ''; // permet de resélectionner la même photo à la suite
        if (!file) return;
        if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
        setImageFile(file);
        setImagePreviewUrl(URL.createObjectURL(file));
    };

    const clearImage = () => {
        if (imagePreviewUrl) URL.revokeObjectURL(imagePreviewUrl);
        setImageFile(null);
        setImagePreviewUrl(null);
    };

    const handleSend = () => {
        if ((!input.trim() && !imageFile) || sending) return;
        sendMessage(input, imageFile);
        setInput('');
        clearImage();
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend();
        }
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

                {messages.map(m => (
                    <ChatBubble
                        key={m.id}
                        role={m.role}
                        text={m.displayText}
                        attachedImage={m.attachedImagePartIndex != null ? m.parts?.[m.attachedImagePartIndex]?.inlineData : null}
                    />
                ))}

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
                {imagePreviewUrl && (
                    <div className="relative inline-block mb-2">
                        <img src={imagePreviewUrl} alt="Photo à envoyer" className="h-16 w-16 object-cover rounded-lg border border-slate-700" />
                        <button
                            onClick={clearImage}
                            className="absolute -top-1.5 -right-1.5 w-5 h-5 flex items-center justify-center rounded-full bg-slate-900 border border-slate-700 text-slate-400 hover:text-white hover:bg-rose-600 hover:border-rose-600 transition-colors"
                            title="Retirer la photo"
                        >
                            <X size={12} />
                        </button>
                    </div>
                )}
                <div className="flex items-end gap-2">
                    {/* Pas d'attribut `capture` : sur plusieurs navigateurs mobiles (Android
                        Chrome/WebView notamment), `capture="environment"` ouvre l'appareil photo
                        directement et retire l'option galerie du sélecteur — alors que la feature
                        doit permettre les deux (photo prise sur place OU choisie dans la galerie).
                        Sans cet attribut, le sélecteur natif propose Caméra ET Fichiers/Galerie. */}
                    <input
                        ref={fileInputRef}
                        type="file"
                        accept="image/*"
                        onChange={handlePickImage}
                        className="hidden"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={loading || sending}
                        className="w-10 h-10 shrink-0 flex items-center justify-center rounded-xl bg-slate-800 border border-slate-700 hover:bg-slate-700 text-slate-400 hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        title="Joindre une photo"
                    >
                        <Paperclip size={16} />
                    </button>
                    <textarea
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={loading || sending}
                        placeholder="Ta question..."
                        rows={1}
                        className="flex-1 resize-none bg-slate-800 border border-slate-700 rounded-xl px-3 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500 transition-all disabled:opacity-50"
                    />
                    <button
                        onClick={handleSend}
                        disabled={loading || sending || (!input.trim() && !imageFile)}
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
