import React, { useState, useEffect } from 'react';
import { collectionGroup, getDocs, doc, getDoc, updateDoc, deleteDoc, collection } from 'firebase/firestore';
import { X, ShieldCheck, RefreshCw, AlertTriangle, Pause, Clock, Trash2 } from 'lucide-react';
import { db } from '../services/firebase';

const APP_ID = import.meta.env.VITE_APP_ID_TARGET;

const formatDate = (ts) => {
    if (!ts) return '—';
    try {
        const date = ts?.toDate ? ts.toDate() : new Date(ts);
        return date.toLocaleString('fr-CA', { dateStyle: 'short', timeStyle: 'short' });
    } catch {
        return '—';
    }
};

const STATUS_COLOR = {
    scanning: 'text-blue-400 bg-blue-500/10',
    scanning_url: 'text-blue-400 bg-blue-500/10',
    idle: 'text-amber-400 bg-amber-500/10',
    paused: 'text-slate-400 bg-slate-500/10',
    stopped: 'text-rose-400 bg-rose-500/10',
};

const AdminDashboard = ({ onClose }) => {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [statsComputedAt, setStatsComputedAt] = useState(null);

    const loadData = async () => {
        setLoading(true);
        setError(null);
        try {
            // Nécessite le custom claim admin (règle Firestore isAdmin() sur collectionGroup('users')).
            const usersSnap = await getDocs(collectionGroup(db, 'users'));

            let statsByUser = {};
            try {
                const statsDoc = await getDoc(doc(db, 'artifacts', APP_ID, 'admin_stats', 'latest'));
                if (statsDoc.exists()) {
                    statsByUser = statsDoc.data().users || {};
                    setStatsComputedAt(statsDoc.data().computedAt);
                }
            } catch (e) {
                // Pas bloquant : le tableau reste utilisable sans les stats de coût/volume.
                console.warn('admin_stats indisponible :', e.message);
            }

            const merged = await Promise.all(usersSnap.docs
                // collectionGroup('users') retourne toute collection nommée "users" dans la base,
                // quel que soit l'appId parent — on ne garde que celle de cette app.
                .filter(d => d.ref.parent.parent?.id === APP_ID)
                .map(async (d) => {
                    const data = d.data();
                    const stats = statsByUser[d.id] || {};
                    
                    let citiesCount = 0;
                    try {
                        const citiesSnap = await getDocs(collection(db, 'artifacts', APP_ID, 'users', d.id, 'cities'));
                        citiesCount = citiesSnap.size;
                    } catch (e) {
                        console.warn(`Erreur lecture cities pour ${d.id}:`, e);
                    }

                    return {
                        uid: d.id,
                        email: data.email || '—',
                        createdAt: data.createdAt,
                        lastLogin: data.lastLogin || data.lastSeen,
                        botStatus: data.botStatus || 'inconnu',
                        scanFrequency: data.scanConfig?.frequency,
                        maxListings: data.scanConfig?.max_listings || 0,
                        citiesCount,
                        dailyVolume: stats.dailyVolume ?? null,
                        reachedT2: stats.reachedT2 ?? null,
                        reachedT3: stats.reachedT3 ?? null,
                        estimatedDailyCost: stats.estimatedDailyCost ?? null,
                    };
                }));

            setRows(merged);
        } catch (e) {
            console.error('Erreur chargement AdminDashboard:', e);
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    const handlePauseUser = async (uid) => {
        try {
            await updateDoc(doc(db, 'artifacts', APP_ID, 'users', uid), { botStatus: 'paused' });
            loadData();
        } catch (e) {
            alert('Erreur: ' + e.message);
        }
    };

    const handleChangeFreq = async (uid, currentFreq) => {
        const freq = window.prompt("Nouvelle fréquence en minutes :", currentFreq || 60);
        if (freq && !isNaN(freq)) {
            try {
                await updateDoc(doc(db, 'artifacts', APP_ID, 'users', uid), { 'scanConfig.frequency': parseInt(freq, 10) });
                loadData();
            } catch (e) {
                alert('Erreur: ' + e.message);
            }
        }
    };

    const handleDeleteUser = async (uid, email) => {
        if (window.confirm(`Voulez-vous vraiment supprimer les données de l'utilisateur ${email} (uid: ${uid}) ?\n(Ceci ne supprime pas son compte Firebase Auth)`)) {
            try {
                await deleteDoc(doc(db, 'artifacts', APP_ID, 'users', uid));
                loadData();
            } catch (e) {
                alert('Erreur: ' + e.message);
            }
        }
    };

    useEffect(() => { loadData(); }, []);

    return (
        <div className="fixed inset-0 z-[70] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="w-full max-w-6xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden">
                <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 shrink-0">
                    <div className="flex items-center gap-2">
                        <ShieldCheck size={18} className="text-emerald-400" />
                        <h2 className="text-sm font-black text-slate-100 uppercase tracking-wide">Dashboard Administrateur</h2>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={loadData}
                            className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                            title="Rafraîchir"
                        >
                            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
                        </button>
                        <button
                            onClick={onClose}
                            className="p-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-400 hover:text-white hover:bg-slate-700 transition-colors"
                        >
                            <X size={16} />
                        </button>
                    </div>
                </div>

                <div className="overflow-auto flex-1 p-5">
                    {error && (
                        <div className="mb-4 flex items-center gap-2 text-rose-400 bg-rose-500/10 border border-rose-500/20 rounded-xl px-4 py-3 text-sm">
                            <AlertTriangle size={16} className="shrink-0" />
                            {error} — vérifie que le custom claim admin est posé (backend/scripts/set_admin_claim.py) et que les règles Firestore sont déployées.
                        </div>
                    )}

                    {statsComputedAt && (
                        <p className="text-xs text-slate-500 mb-3">
                            Snapshot coût/volume calculé le : {formatDate(statsComputedAt)}
                        </p>
                    )}

                    {loading ? (
                        <div className="py-16 flex items-center justify-center text-slate-500 text-sm">Chargement...</div>
                    ) : rows.length === 0 ? (
                        <div className="py-16 flex items-center justify-center text-slate-500 text-sm">Aucun utilisateur trouvé.</div>
                    ) : (
                        <table className="w-full text-sm text-left">
                            <thead>
                                <tr className="text-[11px] uppercase tracking-wider text-slate-500 border-b border-slate-800">
                                    <th className="pb-2 pr-4">Email</th>
                                    <th className="pb-2 pr-4">UID</th>
                                    <th className="pb-2 pr-4">Créé le</th>
                                    <th className="pb-2 pr-4">Dernier login</th>
                                    <th className="pb-2 pr-4">Statut Bot</th>
                                    <th className="pb-2 pr-4">Fréq. Scan</th>
                                    <th className="pb-2 pr-4">Villes</th>
                                    <th className="pb-2 pr-4">Max Ann.</th>
                                    <th className="pb-2 pr-4">Volume/j</th>
                                    <th className="pb-2 pr-4">T2 / T3</th>
                                    <th className="pb-2 pr-4">Coût est./j</th>
                                    <th className="pb-2">Actions</th>
                                </tr>
                            </thead>
                            <tbody>
                                {rows.map(r => (
                                    <tr key={r.uid} className="border-b border-slate-800/50 text-slate-300">
                                        <td className="py-2 pr-4 font-bold text-slate-200">{r.email}</td>
                                        <td className="py-2 pr-4 font-mono text-[11px] text-slate-500">{r.uid.slice(0, 12)}...</td>
                                        <td className="py-2 pr-4 text-xs">{formatDate(r.createdAt)}</td>
                                        <td className="py-2 pr-4 text-xs">{formatDate(r.lastLogin)}</td>
                                        <td className="py-2 pr-4">
                                            <span className={`px-2 py-0.5 rounded-md text-[11px] font-bold ${STATUS_COLOR[r.botStatus] || 'text-slate-400 bg-slate-500/10'}`}>
                                                {r.botStatus}
                                            </span>
                                        </td>
                                        <td className="py-2 pr-4 text-xs">{r.scanFrequency ? `${r.scanFrequency} min` : '—'}</td>
                                        <td className="py-2 pr-4 text-xs">{r.citiesCount}</td>
                                        <td className="py-2 pr-4 text-xs">{r.maxListings || '—'}</td>
                                        <td className="py-2 pr-4 text-xs">{r.dailyVolume ?? '—'}</td>
                                        <td className="py-2 pr-4 text-xs">{r.reachedT2 ?? '—'} / {r.reachedT3 ?? '—'}</td>
                                        <td className="py-2 pr-4 text-xs">{r.estimatedDailyCost != null ? `$${r.estimatedDailyCost.toFixed(3)}` : '—'}</td>
                                        <td className="py-2 flex items-center gap-1.5">
                                            <button onClick={() => handlePauseUser(r.uid)} className="p-1.5 rounded bg-slate-800 text-slate-400 hover:text-amber-400 hover:bg-amber-400/10 transition-colors" title="Mettre en pause">
                                                <Pause size={14} />
                                            </button>
                                            <button onClick={() => handleChangeFreq(r.uid, r.scanFrequency)} className="p-1.5 rounded bg-slate-800 text-slate-400 hover:text-blue-400 hover:bg-blue-400/10 transition-colors" title="Modifier la fréquence">
                                                <Clock size={14} />
                                            </button>
                                            <button onClick={() => handleDeleteUser(r.uid, r.email)} className="p-1.5 rounded bg-slate-800 text-slate-400 hover:text-rose-400 hover:bg-rose-400/10 transition-colors" title="Supprimer l'utilisateur">
                                                <Trash2 size={14} />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;
