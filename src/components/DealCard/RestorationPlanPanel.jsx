import React, { useState, useRef } from 'react';
import {
    ArrowLeft, Plus, Trash2, Loader2, Pencil, MessageCircle, AlertTriangle, Sparkles,
    GripVertical, Camera, Image as ImageIcon, ImagePlus, X, Check,
} from 'lucide-react';
import {
    DndContext, closestCenter, PointerSensor, TouchSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { RESTORATION_CATEGORY_LABELS as CATEGORY_LABELS, RESTORATION_STATUS_LABELS as STATUS_LABELS } from '../../constants/restorationPlan';

const STATUS_STYLES = {
    pending: 'bg-slate-800 text-slate-300 border-slate-700',
    waiting: 'bg-amber-500/10 text-amber-300 border-amber-500/20',
    in_progress: 'bg-blue-500/10 text-blue-300 border-blue-500/20',
    done: 'bg-emerald-500/10 text-emerald-300 border-emerald-500/20',
    skipped: 'bg-slate-900 text-slate-500 border-slate-800',
};

const emptyForm = { label: '', category: 'autre', estimatedCost: '', notes: '' };

// Formulaire d'édition (ajout ou modification) d'une étape — champs regroupés ici uniquement le
// temps de l'édition (jamais montés en continu) : évite qu'un listener temps réel ne vole le
// curseur au milieu de la frappe, puisque rien ne resynchronise ce brouillon local tant qu'il
// n'est pas explicitement enregistré/annulé.
const ItemForm = ({ initial, onCancel, onSubmit, submitLabel }) => {
    const [form, setForm] = useState(initial);
    const [saving, setSaving] = useState(false);

    const submit = async () => {
        if (!form.label.trim()) return;
        setSaving(true);
        try {
            const parsedCost = parseFloat(form.estimatedCost);
            await onSubmit({
                label: form.label.trim(),
                category: form.category,
                estimatedCost: Number.isFinite(parsedCost) ? parsedCost : null,
                notes: form.notes.trim() || null,
            });
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="bg-slate-950 border border-purple-500/30 rounded-xl p-3 space-y-2">
            <input
                autoFocus
                value={form.label}
                onChange={(e) => setForm(f => ({ ...f, label: e.target.value }))}
                placeholder="Étape (ex: Recoller le binding)"
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
            />
            <div className="flex gap-2">
                <select
                    value={form.category}
                    onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
                    className="flex-1 bg-slate-900 border border-slate-700 rounded-lg px-2 py-2 text-xs text-slate-200 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
                >
                    {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
                        <option key={value} value={value}>{label}</option>
                    ))}
                </select>
                <input
                    type="number"
                    value={form.estimatedCost}
                    onChange={(e) => setForm(f => ({ ...f, estimatedCost: e.target.value }))}
                    placeholder="Coût estimé ($)"
                    className="w-32 bg-slate-900 border border-slate-700 rounded-lg px-2 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/40"
                />
            </div>
            <textarea
                value={form.notes}
                onChange={(e) => setForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="Notes (optionnel)..."
                rows={2}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500/40 resize-none"
            />
            <div className="flex justify-end gap-2">
                <button onClick={onCancel} disabled={saving} className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors disabled:opacity-50">
                    Annuler
                </button>
                <button onClick={submit} disabled={saving || !form.label.trim()} className="px-3 py-1.5 rounded-lg text-xs font-bold text-white bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5">
                    {saving && <Loader2 size={12} className="animate-spin" />}
                    {submitLabel}
                </button>
            </div>
        </div>
    );
};

// Sélecteur de photos déjà existantes dans la galerie de l'annonce (2026-08-22) — clic direct pour
// attacher (pas de bouton "confirmer" séparé, même esprit que ClassificationEditor : une action
// franche plutôt qu'un formulaire à valider). `attached` = URLs déjà attachées à CETTE étape,
// grisées/cochées plutôt que ré-attachables (arrayUnion serait un no-op, mais autant l'afficher).
const GalleryPickerModal = ({ galleryUrls, attached, onPick, onClose }) => (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
        <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl p-4 max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-black text-slate-100">Choisir dans la galerie de l'annonce</h3>
                <button onClick={onClose} className="text-slate-500 hover:text-slate-300"><X size={16} /></button>
            </div>
            {galleryUrls.length === 0 ? (
                <div className="text-xs text-slate-500 py-6 text-center">Aucune photo dans la galerie de cette annonce.</div>
            ) : (
                <div className="grid grid-cols-3 gap-2 overflow-y-auto scrollbar-dark">
                    {galleryUrls.map(url => {
                        const isAttached = attached.includes(url);
                        return (
                            <button
                                key={url}
                                onClick={() => !isAttached && onPick(url)}
                                disabled={isAttached}
                                className="relative aspect-square rounded-lg overflow-hidden border border-slate-700 disabled:cursor-default"
                            >
                                <img src={url} alt="Photo de la galerie" className="w-full h-full object-cover" />
                                {isAttached && (
                                    <div className="absolute inset-0 bg-emerald-900/70 flex items-center justify-center">
                                        <Check size={20} className="text-emerald-300" />
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            )}
        </div>
    </div>
);

const RestorationItem = ({ item, onUpdate, onDelete, onAskInChat, onAddPhoto, onAttachExistingPhoto, onRemovePhoto, galleryUrls }) => {
    const [editing, setEditing] = useState(false);
    const [actualCostDraft, setActualCostDraft] = useState(item.actualCost != null ? String(item.actualCost) : '');
    const [editingActualCost, setEditingActualCost] = useState(false);
    const [busy, setBusy] = useState(false);
    const [showAttachMenu, setShowAttachMenu] = useState(false);
    const [showGalleryPicker, setShowGalleryPicker] = useState(false);
    const [uploadingPhoto, setUploadingPhoto] = useState(false);
    const [removingPhoto, setRemovingPhoto] = useState(null);
    const cameraInputRef = useRef(null);
    const fileInputRef = useRef(null);

    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.id });
    const dragStyle = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };

    // Le mode édition reste dans le MÊME conteneur (ref/style de useSortable) que l'affichage
    // normal — un retour anticipé vers un DOM différent détacherait la ref que dnd-kit utilise
    // pour mesurer/positionner l'item pendant un glisser en cours sur un autre item de la liste.
    if (editing) {
        return (
            <div ref={setNodeRef} style={dragStyle}>
                <ItemForm
                    initial={{
                        label: item.label,
                        category: item.category,
                        estimatedCost: item.estimatedCost != null ? String(item.estimatedCost) : '',
                        notes: item.notes || '',
                    }}
                    submitLabel="Enregistrer"
                    onCancel={() => setEditing(false)}
                    onSubmit={async (data) => { await onUpdate(item.id, data); setEditing(false); }}
                />
            </div>
        );
    }

    const saveActualCost = async () => {
        const parsed = parseFloat(actualCostDraft);
        setBusy(true);
        try {
            await onUpdate(item.id, { actualCost: Number.isFinite(parsed) ? parsed : null });
            setEditingActualCost(false);
        } finally {
            setBusy(false);
        }
    };

    const handlePickFiles = async (e) => {
        const files = Array.from(e.target.files || []);
        e.target.value = '';
        if (!files.length) return;
        setUploadingPhoto(true);
        try {
            await Promise.all(files.map(f => onAddPhoto(item.id, f)));
        } catch (err) {
            console.error('Erreur upload photo étape:', err);
        } finally {
            setUploadingPhoto(false);
        }
    };

    const handleRemovePhoto = async (url) => {
        setRemovingPhoto(url);
        try {
            await onRemovePhoto(item.id, url);
        } finally {
            setRemovingPhoto(null);
        }
    };

    const photoUrls = item.photoUrls || [];

    return (
        <div ref={setNodeRef} style={dragStyle} className="bg-slate-950 border border-slate-800 rounded-xl p-3">
            <div className="flex items-start gap-2">
                <button
                    {...attributes}
                    {...listeners}
                    title="Glisser pour réorganiser"
                    className="mt-0.5 text-slate-600 hover:text-slate-400 cursor-grab active:cursor-grabbing shrink-0 touch-none"
                >
                    <GripVertical size={16} />
                </button>
                <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                            <div className="text-sm font-bold text-slate-200 break-words">{item.label}</div>
                            <div className="flex flex-wrap items-center gap-1.5 mt-1">
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 uppercase font-bold tracking-wide">
                                    {CATEGORY_LABELS[item.category] || item.category}
                                </span>
                                {item.estimatedCost != null && (
                                    <span className="text-[10px] text-slate-500">≈ {item.estimatedCost}$ estimé</span>
                                )}
                            </div>
                            {item.notes && <div className="text-xs text-slate-400 mt-1.5 whitespace-pre-wrap">{item.notes}</div>}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                            <button onClick={() => onAskInChat(item)} title="Demander conseil dans le chat" className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-purple-400 hover:bg-purple-500/10 transition-colors">
                                <MessageCircle size={14} />
                            </button>
                            <button onClick={() => setEditing(true)} title="Modifier" className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-blue-400 hover:bg-blue-500/10 transition-colors">
                                <Pencil size={13} />
                            </button>
                            <button onClick={() => onDelete(item.id)} title="Supprimer" className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors">
                                <Trash2 size={13} />
                            </button>
                        </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2 mt-2.5">
                        <select
                            value={item.status}
                            onChange={(e) => onUpdate(item.id, { status: e.target.value })}
                            className={`text-[11px] font-bold rounded-lg px-2 py-1 border focus:outline-none ${STATUS_STYLES[item.status]}`}
                        >
                            {Object.entries(STATUS_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                        {item.status === 'done' && (
                            editingActualCost ? (
                                <div className="flex items-center gap-1">
                                    <input
                                        autoFocus
                                        type="number"
                                        value={actualCostDraft}
                                        onChange={(e) => setActualCostDraft(e.target.value)}
                                        placeholder="Coût réel ($)"
                                        className="w-24 bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                                    />
                                    <button onClick={saveActualCost} disabled={busy} className="text-[11px] font-bold text-emerald-400 hover:text-emerald-300 disabled:opacity-50">OK</button>
                                </div>
                            ) : (
                                <button onClick={() => setEditingActualCost(true)} className="text-[11px] text-emerald-400 hover:text-emerald-300">
                                    {item.actualCost != null ? `Coût réel : ${item.actualCost}$` : 'Ajouter le coût réel'}
                                </button>
                            )
                        )}
                    </div>

                    {/* Photos (2026-08-22) — upload direct ou photo déjà dans la galerie de l'annonce */}
                    <div className="flex flex-wrap items-center gap-2 mt-2.5">
                        {photoUrls.map(url => (
                            <div key={url} className="relative">
                                <a href={url} target="_blank" rel="noopener noreferrer">
                                    <img src={url} alt="Photo de l'étape" className="w-14 h-14 object-cover rounded-lg border border-slate-700" />
                                </a>
                                <button
                                    onClick={() => handleRemovePhoto(url)}
                                    disabled={removingPhoto === url}
                                    className="absolute -top-1.5 -right-1.5 w-5 h-5 flex items-center justify-center rounded-full bg-slate-900 border border-slate-700 text-slate-400 hover:text-white hover:bg-rose-600 hover:border-rose-600 transition-colors disabled:opacity-50"
                                    title="Retirer la photo"
                                >
                                    {removingPhoto === url ? <Loader2 size={10} className="animate-spin" /> : <X size={10} />}
                                </button>
                            </div>
                        ))}

                        <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" onChange={handlePickFiles} className="hidden" />
                        <input ref={fileInputRef} type="file" accept="image/*" multiple onChange={handlePickFiles} className="hidden" />

                        <div className="relative">
                            <button
                                onClick={() => setShowAttachMenu(v => !v)}
                                disabled={uploadingPhoto}
                                title="Ajouter une photo"
                                className="w-14 h-14 flex items-center justify-center rounded-lg border border-dashed border-slate-700 text-slate-500 hover:text-purple-400 hover:border-purple-500/50 transition-colors disabled:opacity-50"
                            >
                                {uploadingPhoto ? <Loader2 size={16} className="animate-spin" /> : <ImagePlus size={16} />}
                            </button>
                            {showAttachMenu && (
                                <>
                                    <div className="fixed inset-0 z-40" onClick={() => setShowAttachMenu(false)} />
                                    <div className="absolute bottom-full left-0 mb-2 w-60 z-50">
                                        <div className="bg-slate-800 border border-slate-700 rounded-xl shadow-[0_10px_40px_-10px_rgba(0,0,0,0.8)] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
                                            <button
                                                onClick={() => { setShowAttachMenu(false); cameraInputRef.current?.click(); }}
                                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                                            >
                                                <Camera size={15} /> Prendre une photo
                                            </button>
                                            <button
                                                onClick={() => { setShowAttachMenu(false); fileInputRef.current?.click(); }}
                                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 border-b border-slate-700/50 transition-colors"
                                            >
                                                <ImageIcon size={15} /> Choisir depuis le téléphone
                                            </button>
                                            <button
                                                onClick={() => { setShowAttachMenu(false); setShowGalleryPicker(true); }}
                                                className="w-full px-4 py-2.5 text-left text-sm font-bold text-slate-200 hover:bg-slate-700 hover:text-white flex items-center gap-2 transition-colors"
                                            >
                                                <ImagePlus size={15} /> Choisir dans la galerie de l'annonce
                                            </button>
                                        </div>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {showGalleryPicker && (
                <GalleryPickerModal
                    galleryUrls={galleryUrls}
                    attached={photoUrls}
                    onPick={(url) => onAttachExistingPhoto(item.id, url)}
                    onClose={() => setShowGalleryPicker(false)}
                />
            )}
        </div>
    );
};

const FAIRE_LE_POINT_PROMPT = "Fais le point sur l'état actuel de la restauration : qu'est-ce qu'il reste à faire, et pour quel coût estimé ?";
const PREPARER_ANNONCE_PROMPT = "Rédige une description d'annonce Marketplace pour revendre cette guitare, en valorisant les travaux de restauration effectués.";

const RestorationPlanPanel = ({ deal, plan, onBack, onAskInChat, onQuickPrompt }) => {
    const { items, loading, error, addItem, updateItem, deleteItem, reorderItems, addPhoto, attachExistingPhoto, removePhoto, totals } = plan;
    const [showAddForm, setShowAddForm] = useState(false);

    // Distance minimale avant d'activer le glisser (souris) et léger délai + tolérance (tactile) —
    // évite qu'un simple tap sur la poignée ou un clic déclenche un drag involontaire.
    const sensors = useSensors(
        useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
        useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 8 } }),
    );

    const handleDragEnd = (event) => {
        const { active, over } = event;
        if (!over || active.id === over.id) return;
        const oldIndex = items.findIndex(i => i.id === active.id);
        const newIndex = items.findIndex(i => i.id === over.id);
        if (oldIndex === -1 || newIndex === -1) return;
        reorderItems(arrayMove(items, oldIndex, newIndex).map(i => i.id));
    };

    const ai = deal.aiAnalysis || {};
    const targetValue = ai.resale_potential ?? ai.estimated_value ?? ai.estimated_guitar_value ?? null;
    const costBasis = deal.purchasePrice ?? deal.price ?? null;
    const projectedMargin = (targetValue != null && costBasis != null)
        ? Math.round(targetValue - costBasis - totals.totalEstimatedCost)
        : null;
    const galleryUrls = (deal.storageImageUrls || []).filter(Boolean);

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
                    <h3 className="text-sm font-black text-white truncate">Plan de restauration</h3>
                    <p className="text-[11px] text-slate-500 truncate">{deal.title}</p>
                </div>
            </div>

            <div className="flex-1 min-h-0 overflow-y-auto p-4 scrollbar-dark">
                {/* Summary bar */}
                <div className="flex flex-wrap items-center gap-3 mb-4">
                    <div className="bg-slate-950 px-3 py-2 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-500 font-bold uppercase">Étapes</div>
                        <div className="text-sm font-black text-white">{totals.doneCount}/{totals.itemCount} terminées</div>
                    </div>
                    <div className="bg-slate-950 px-3 py-2 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-500 font-bold uppercase">Coût total estimé</div>
                        <div className="text-sm font-black text-white">{totals.totalEstimatedCost}$</div>
                    </div>
                    <div className="bg-slate-950 px-3 py-2 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-500 font-bold uppercase">Dépensé à date</div>
                        <div className="text-sm font-black text-white">{totals.spentCost}$</div>
                    </div>
                    <div className="bg-slate-950 px-3 py-2 rounded-xl border border-slate-800">
                        <div className="text-[10px] text-slate-500 font-bold uppercase">Reste à payer</div>
                        <div className="text-sm font-black text-white">{totals.remainingCost}$</div>
                    </div>
                    {projectedMargin != null && (
                        <div className={`px-3 py-2 rounded-xl border ${projectedMargin > 0 ? 'bg-emerald-500/10 border-emerald-500/20' : 'bg-rose-500/10 border-rose-500/20'}`}>
                            <div className={`text-[10px] font-bold uppercase ${projectedMargin > 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>
                                Marge nette projetée après restauration
                            </div>
                            <div className={`text-sm font-black ${projectedMargin > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {projectedMargin > 0 ? '+' : ''}{projectedMargin}$
                            </div>
                            <div className="text-[10px] text-slate-500 mt-0.5">
                                {targetValue}$ (revente visée) − {costBasis}$ (payé) − {totals.totalEstimatedCost}$ (travaux)
                                {deal.purchasePrice == null && <span className="text-amber-500"> · prix payé non précisé, prix demandé utilisé</span>}
                            </div>
                        </div>
                    )}
                </div>

                {/* Prompts prédéfinis (2026-08-22, Lot B) — envoyés directement dans le chat
                    (aucune écriture sur le plan lui-même, juste une question posée à Gemini,
                    qui reçoit déjà le contexte du plan à chaque tour). */}
                <div className="flex flex-wrap gap-2 mb-4">
                    <button
                        onClick={() => onQuickPrompt(FAIRE_LE_POINT_PROMPT)}
                        className="flex items-center gap-1.5 text-xs font-bold text-purple-300 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 rounded-lg px-3 py-1.5 transition-colors"
                    >
                        <Sparkles size={12} /> Faire le point
                    </button>
                    <button
                        onClick={() => onQuickPrompt(PREPARER_ANNONCE_PROMPT)}
                        className="flex items-center gap-1.5 text-xs font-bold text-purple-300 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 rounded-lg px-3 py-1.5 transition-colors"
                    >
                        <Sparkles size={12} /> Préparer l'annonce de revente
                    </button>
                </div>

                {error && (
                    <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs rounded-xl px-3 py-2 mb-3">
                        <AlertTriangle size={14} className="shrink-0" />
                        <span>{error}</span>
                    </div>
                )}

                {loading && (
                    <div className="flex items-center justify-center py-8 text-slate-500 text-sm gap-2">
                        <Loader2 size={16} className="animate-spin" /> Chargement du plan...
                    </div>
                )}

                {!loading && items.length === 0 && !showAddForm && (
                    <div className="text-center text-slate-500 text-sm py-8 px-4">
                        Aucune étape pour l'instant — ajoute la première ci-dessous, ou discute avec Gemini pour affiner tes constats.
                    </div>
                )}

                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                    <SortableContext items={items.map(i => i.id)} strategy={verticalListSortingStrategy}>
                        <div className="space-y-2 mb-3">
                            {items.map(item => (
                                <RestorationItem
                                    key={item.id}
                                    item={item}
                                    onUpdate={updateItem}
                                    onDelete={deleteItem}
                                    onAskInChat={onAskInChat}
                                    onAddPhoto={addPhoto}
                                    onAttachExistingPhoto={attachExistingPhoto}
                                    onRemovePhoto={removePhoto}
                                    galleryUrls={galleryUrls}
                                />
                            ))}
                        </div>
                    </SortableContext>
                </DndContext>

                {showAddForm ? (
                    <ItemForm
                        initial={emptyForm}
                        submitLabel="Ajouter"
                        onCancel={() => setShowAddForm(false)}
                        onSubmit={async (data) => { await addItem(data); setShowAddForm(false); }}
                    />
                ) : (
                    <button
                        onClick={() => setShowAddForm(true)}
                        className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl border border-dashed border-slate-700 text-slate-400 hover:text-white hover:border-purple-500/50 hover:bg-purple-500/5 transition-colors text-sm font-bold"
                    >
                        <Plus size={15} /> Ajouter une étape
                    </button>
                )}
            </div>
        </div>
    );
};

export default RestorationPlanPanel;
