import { useState, useEffect, useCallback, useMemo } from 'react';
import { onRestorationPlanUpdate, addRestorationItem, updateRestorationItem, deleteRestorationItem } from '../services/firestoreService';

// Statuts non terminaux comptés dans `remainingCost` — tout ce qui n'est ni `done` ni `skipped`.
const OPEN_STATUSES = ['pending', 'waiting', 'in_progress'];

// Gère le plan de restauration (sous-collection guitar_deals/{dealId}/restorationPlan) d'une
// annonce achetée. Monté dans DealAnalysisModal.jsx plutôt que dans le panneau lui-même — la puce
// de résumé affichée hors du panneau (bloc "Achetée") a besoin du plan même quand le panneau est
// fermé, et le futur Lot B (function calling) en aura besoin dans useDealChat::sendMessage. Un
// seul listener par modale ouverte, contrairement à useDealChat qui vit dans DealChatPanel.jsx
// car rien d'autre n'a besoin des messages.
export const useRestorationPlan = (deal, user) => {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const active = !!(deal?.id && user && deal.isPurchased);

    useEffect(() => {
        if (!active) {
            setItems([]);
            setLoading(false);
            return;
        }
        setLoading(true);
        const unsubscribe = onRestorationPlanUpdate(deal.id, (list) => {
            setItems(list);
            setLoading(false);
        }, (e) => { setError(e.message); setLoading(false); }, user.uid);
        return () => unsubscribe();
    }, [active, deal?.id, user]);

    const addItem = useCallback(async (itemData) => {
        if (!active) return;
        await addRestorationItem(deal.id, user.uid, itemData);
    }, [active, deal?.id, user]);

    const updateItem = useCallback(async (itemId, patch) => {
        if (!active) return;
        await updateRestorationItem(deal.id, user.uid, itemId, patch);
    }, [active, deal?.id, user]);

    const deleteItem = useCallback(async (itemId) => {
        if (!active) return;
        await deleteRestorationItem(deal.id, user.uid, itemId);
    }, [active, deal?.id, user]);

    // Sémantique figée avec le plan : totalEstimatedCost exclut `skipped` ; remainingCost ne
    // compte que les statuts non terminaux ; spentCost (coût réel, sinon estimé) ne porte que sur
    // les étapes `done`.
    const totals = useMemo(() => {
        let totalEstimatedCost = 0;
        let remainingCost = 0;
        let spentCost = 0;
        let doneCount = 0;
        for (const item of items) {
            const est = item.estimatedCost ?? 0;
            if (item.status !== 'skipped') totalEstimatedCost += est;
            if (OPEN_STATUSES.includes(item.status)) remainingCost += est;
            if (item.status === 'done') {
                doneCount++;
                spentCost += item.actualCost ?? est;
            }
        }
        return { itemCount: items.length, doneCount, totalEstimatedCost, remainingCost, spentCost };
    }, [items]);

    return { items, loading, error, addItem, updateItem, deleteItem, totals };
};
