import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
    onRestorationPlanUpdate, addRestorationItem, updateRestorationItem, deleteRestorationItem,
    backfillRestorationOrder, addRestorationItemPhoto, removeRestorationItemPhoto,
} from '../services/firestoreService';
import { uploadRestorationPhotoToDealStorage } from '../services/storageService';

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
    // Évite de relancer le backfill d'ordre à chaque snapshot tant que le batch précédent n'a pas
    // encore fait revenir des items tous pourvus d'un `order` (fire-and-forget côté écriture, pas
    // de retour synchrone à attendre autrement).
    const backfillingRef = useRef(false);

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
            // Réorganisation par glisser-déposer (2026-08-22) : `order` n'existe pas sur les items
            // créés avant cette fonctionnalité (ou tout juste ajoutés). Jamais de migration
            // explicite — le premier client qui charge un plan où au moins un item n'a pas `order`
            // le rattrape pour TOUS les items d'un coup (jamais un mélange ordonnés/non-ordonnés),
            // selon l'ordre d'affichage courant (`createdAt`, déjà l'ordre de la requête Firestore).
            if (!backfillingRef.current && list.length > 1 && list.some(i => i.order == null)) {
                backfillingRef.current = true;
                backfillRestorationOrder(deal.id, user.uid, list).finally(() => { backfillingRef.current = false; });
            }
        }, (e) => { setError(e.message); setLoading(false); }, user.uid);
        return () => unsubscribe();
    }, [active, deal?.id, user]);

    // Trié par `order` une fois tous les items pourvus ; sinon (le temps du backfill ci-dessus) on
    // garde l'ordre `createdAt` déjà renvoyé par la requête Firestore, déjà correct.
    const sortedItems = useMemo(() => {
        return items.every(i => i.order != null)
            ? [...items].sort((a, b) => a.order - b.order)
            : items;
    }, [items]);

    const addItem = useCallback(async (itemData) => {
        if (!active) return;
        // `order` calculé ici, sur la liste déjà en mémoire (aucune lecture Firestore
        // supplémentaire) — sans lui, l'item créé sans `order` redéclenchait le rattrapage
        // silencieux (backfillRestorationOrder) sur TOUT le plan, effaçant un ordre de
        // glisser-déposer déjà mis en place par l'utilisateur (bug trouvé en revue, corrigé ici).
        const order = items.length ? Math.max(...items.map(i => i.order ?? -1)) + 1 : 0;
        await addRestorationItem(deal.id, user.uid, { ...itemData, order });
    }, [active, deal?.id, user, items]);

    const updateItem = useCallback(async (itemId, patch) => {
        if (!active) return;
        await updateRestorationItem(deal.id, user.uid, itemId, patch);
    }, [active, deal?.id, user]);

    const deleteItem = useCallback(async (itemId) => {
        if (!active) return;
        await deleteRestorationItem(deal.id, user.uid, itemId);
    }, [active, deal?.id, user]);

    // Persiste un nouvel ordre après un glisser-déposer — `orderedIds` = ids dans le nouvel ordre
    // d'affichage voulu, réutilise `updateItem` (déjà champ par champ) plutôt qu'une écriture dédiée.
    const reorderItems = useCallback(async (orderedIds) => {
        if (!active) return;
        await Promise.all(orderedIds.map((id, index) => updateRestorationItem(deal.id, user.uid, id, { order: index })));
    }, [active, deal?.id, user]);

    // Upload direct d'une nouvelle photo (prise sur place ou choisie dans la galerie du téléphone)
    // et attachement d'une photo déjà existante dans la galerie de l'annonce — deux sources, un
    // seul champ d'arrivée (`photoUrls`, voir addRestorationItemPhoto).
    const addPhoto = useCallback(async (itemId, file) => {
        if (!active) return;
        const url = await uploadRestorationPhotoToDealStorage(deal.id, file, file.type || 'image/jpeg');
        await addRestorationItemPhoto(deal.id, user.uid, itemId, url);
        return url;
    }, [active, deal?.id, user]);

    const attachExistingPhoto = useCallback(async (itemId, url) => {
        if (!active) return;
        await addRestorationItemPhoto(deal.id, user.uid, itemId, url);
    }, [active, deal?.id, user]);

    const removePhoto = useCallback(async (itemId, url) => {
        if (!active) return;
        await removeRestorationItemPhoto(deal.id, user.uid, itemId, url);
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

    return {
        items: sortedItems, loading, error, addItem, updateItem, deleteItem, reorderItems,
        addPhoto, attachExistingPhoto, removePhoto, totals,
    };
};
