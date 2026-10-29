// Recherche des fiches techniques utiles pour une question, SANS jamais retarder ni casser le chat : délai maximal, annulation
// réelle de la requête, et disjoncteur — un service qui répond mal ne coûte pas son délai à CHAQUE envoi. Fonction pure (la
// requête réelle est injectée) : testée avec `node --test` (src/utils/fichesLookup.test.js).

/** `fetchFiches(dealId, { q, limit, signal })` → promesse d'une liste. Renvoie `lookup(dealId, question)` qui rend TOUJOURS une
 *  liste (vide en cas de délai dépassé, d'erreur ou pendant le disjoncteur). */
export const createFichesLookup = (fetchFiches, { timeoutMs = 2500, backoffMs = 60 * 1000, limit = 4, now = Date.now, warn = console.warn } = {}) => {
    let blockedUntil = 0;
    return async (dealId, question) => {
        if (now() < blockedUntil) return [];
        const controller = new AbortController();
        let timer;
        try {
            const timeout = new Promise((_, reject) => {
                timer = setTimeout(() => { controller.abort(); reject(new Error('délai dépassé')); }, timeoutMs);
            });
            // L'abandon du signal annule la requête ; la course garantit en plus qu'on ne reste pas bloqué si elle l'ignorait.
            const fiches = await Promise.race([fetchFiches(dealId, { q: question, limit, signal: controller.signal }), timeout]);
            return Array.isArray(fiches) ? fiches : [];
        } catch (e) {
            blockedUntil = now() + backoffMs;
            warn('Fiches techniques indisponibles pour ce tour :', e?.message);
            return [];
        } finally {
            clearTimeout(timer);
        }
    };
};
