import React, { useState } from 'react';
import { ArrowLeft, Plus, Trash2, Loader2, Pencil, MessageCircle, AlertTriangle } from 'lucide-react';

const CATEGORY_LABELS = {
    structurel: 'Structurel',
    cosmetique: 'Cosmétique',
    electronique: 'Électronique',
    quincaillerie: 'Quincaillerie',
    reglage: 'Réglage',
    autre: 'Autre',
};

const STATUS_LABELS = {
    pending: 'À faire',
    waiting: 'En attente',
    in_progress: 'En cours',
    done: 'Terminé',
    skipped: 'Ignoré',
};

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

const RestorationItem = ({ item, onUpdate, onDelete, onAskInChat }) => {
    const [editing, setEditing] = useState(false);
    const [actualCostDraft, setActualCostDraft] = useState(item.actualCost != null ? String(item.actualCost) : '');
    const [editingActualCost, setEditingActualCost] = useState(false);
    const [busy, setBusy] = useState(false);

    if (editing) {
        return (
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

    return (
        <div className="bg-slate-950 border border-slate-800 rounded-xl p-3">
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
        </div>
    );
};

const RestorationPlanPanel = ({ deal, plan, onBack, onAskInChat }) => {
    const { items, loading, error, addItem, updateItem, deleteItem, totals } = plan;
    const [showAddForm, setShowAddForm] = useState(false);

    const ai = deal.aiAnalysis || {};
    const targetValue = ai.resale_potential ?? ai.estimated_value ?? ai.estimated_guitar_value ?? null;
    const costBasis = deal.purchasePrice ?? deal.price ?? null;
    const projectedMargin = (targetValue != null && costBasis != null)
        ? Math.round(targetValue - costBasis - totals.totalEstimatedCost)
        : null;

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

                <div className="space-y-2 mb-3">
                    {items.map(item => (
                        <RestorationItem
                            key={item.id}
                            item={item}
                            onUpdate={updateItem}
                            onDelete={deleteItem}
                            onAskInChat={onAskInChat}
                        />
                    ))}
                </div>

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
