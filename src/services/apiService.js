/**
 * Client REST/WebSocket vers `backend/api/*` (Postgres) — Phase A.2 du Chantier A. Mêmes noms de
 * fonctions et mêmes signatures que `firestoreService.js` pour permettre un remplacement de
 * l'import sans toucher aux hooks/composants consommateurs, une fois la bascule décidée
 * (voir docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §5.3).
 *
 * CÂBLÉ DEPUIS LE 2026-09-12 (commit `43991a6`) dans `useDealsManager.js`, `useBotConfig.js`,
 * `useCities.js`, `useDealChat.js`, `useRestorationPlan.js`, `DealCardActions.jsx`,
 * `LogViewer.jsx`, `Navbar.jsx`, `SharedDealPage.jsx` — CETTE MENTION EST RESTÉE FAUSSE
 * ("construit en isolation, importé par AUCUN...") PENDANT PLUS D'UNE SEMAINE après le câblage
 * réel, jamais mise à jour (trouvé le 2026-09-21). Ne pas répéter l'erreur : ce fichier n'est PAS
 * isolé, toute modification ici a un effet direct sur l'app une fois buildée/déployée. Toujours
 * aucun test en conditions réelles (vrai token Firebase, vrai navigateur) depuis cet
 * environnement de dev — à faire avant toute décision de bascule/déploiement, pas supposé sans
 * l'avoir vérifié (leçon de l'incident de production du 2026-09-19, `JOURNAL.md`).
 *
 * Firebase Auth reste inchangé (plan §1) : chaque appel s'authentifie avec le même ID token
 * Firebase que Firestore utilisait déjà en interne — porté explicitement ici (en-tête
 * `Authorization`, ou `?token=` pour les WebSockets qui ne peuvent pas poser d'en-tête custom).
 *
 * Différences assumées avec firestoreService.js (le contrat externe des fonctions ne change pas,
 * sauf mention explicite ci-dessous) :
 * - `deals_index` (sharding Firestore, 20 chunks) n'a pas d'équivalent Postgres (colonnes
 *   indexées nativement, voir schema.sql) : `onDealsIndexUpdate` livre désormais des annonces
 *   COMPLETES (mêmes clés que `fetchDealsByIds`, voir `dealFromRow`), pas la forme abrégée
 *   `p`/`la`/`lo`/`l`/`v`/... — `useDealsManager.js` devra être adapté à ces clés au câblage réel,
 *   hors du périmètre de cette construction isolée.
 * - `chunkId` (paramètre historique de sharding) est accepté partout où il apparaissait encore,
 *   pour ne changer la signature d'aucune fonction appelante, mais toujours ignoré.
 * - Les ids de message de chat / d'étape de restauration sont des entiers (BIGSERIAL Postgres),
 *   pas des chaînes Firestore — transparent pour un appelant qui se contente de les
 *   round-tripper (comparaison, clé React, segment d'URL), jamais d'en parser le format.
 * - `migrateOldDataToNewUser` (copie ponctuelle Firestore -> Firestore d'un ancien compte admin
 *   vers un nouveau, propre à la précédente transition mono- vers multi-utilisateur) reste
 *   IMPORTÉE DEPUIS `firestoreService.js` par `useBotConfig.js` — aucun équivalent Postgres,
 *   opération historique sans rapport avec cette bascule.
 * - Notifications temps réel : le canal WebSocket ne pousse qu'un signal "quelque chose a
 *   changé" (canal partagé, filtré côté serveur par la VISIBILITÉ de l'utilisateur sur ce
 *   deal_id — `user_deal_matches`, voir main.py::ws_deals::_push_if_visible —, pas par un
 *   user_id porté dans le payload), jamais le contenu — chaque callback déclenche un ré-appel de
 *   la lecture REST correspondante, à l'inverse d'`onSnapshot` qui livrait déjà les documents
 *   complets à chaque changement.
 * - `guitar_deals`/`deal_chat`/`restoration_plan_items` sont stockés en colonnes snake_case côté
 *   Postgres (voir schema.sql) : ce fichier reconstruit la forme camelCase + `aiAnalysis` imbriqué
 *   que le reste du frontend consomme déjà (`dealFromRow`/`chatMessageFromRow`/
 *   `restorationItemFromRow`), plutôt que de renvoyer les lignes API brutes.
 * - MIS À JOUR 2026-09-21 pour le catalogue PARTAGÉ (voir JOURNAL.md 2026-09-19/20, backend/api/
 *   deals_repo.py) : `guitar_deals` n'a plus `user_id`/`is_favorite`/de colonne de rejet propres
 *   à un utilisateur — favori et rejet manuel vivent désormais dans `user_deal_state`, exposés
 *   par l'API sous les MÊMES clés `is_favorite`/`is_rejected` qu'avant (voir
 *   `deals_repo.py::_PREFERENCE_SELECT`), donc transparents ici. Seule exception : le rejet
 *   manuel ne touche plus `guitar_deals.status` (réservé au rejet AUTOMATIQUE par verdict IA,
 *   catalogue partagé oblige — un rejet par un utilisateur ne doit pas cacher l'annonce aux
 *   autres) — `dealFromRow` ci-dessous synthétise encore `status: 'rejected'` /
 *   `aiAnalysis.verdict: 'REJECTED'` à partir de `is_rejected` pour ne rien changer côté
 *   `useDealsManager.js`/`DealsExplorer.jsx`, qui filtrent toujours sur ces deux champs (même
 *   contrat que l'ancien `firestoreService.js::rejectDeal`). L'achat reste GLOBAL et peut
 *   désormais échouer avec un 409 (`toggleDealPurchased` ci-dessous) si un AUTRE utilisateur a
 *   acheté l'annonce entre-temps — nouveau cas d'erreur qui n'existait pas dans l'ancien schéma
 *   par utilisateur.
 */
import { auth } from './firebase';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws');
const API_TIMEOUT_MS = 20000;
const WS_RETRY_DELAY_MS = 1000;
const WS_RETRY_DELAY_MAX_MS = 30000;

// --- Helper: Unflatten dot notation to nested objects (copié de firestoreService.js — même
// besoin ici pour updateUserConfig, aucune dépendance Firestore dans cette fonction pure) ---
const unflatten = (data) => {
  if (Object(data) !== data || Array.isArray(data)) return data;
  const result = {};
  for (const p in data) {
    let cur = result, prop = "", parts = p.split(".");
    for (let i = 0; i < parts.length; i++) {
      let idx = !isNaN(parseInt(parts[i]));
      cur = cur[prop] || (cur[prop] = (idx ? [] : {}));
      prop = parts[i];
    }
    cur[prop] = data[p];
  }
  return result[""] || result;
};

async function getIdToken() {
  const user = auth.currentUser;
  if (!user) throw new Error('apiService: aucun utilisateur Firebase connecté.');
  return user.getIdToken();
}

async function apiFetch(path, { method = 'GET', body, skipAuth = false } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (!skipAuth) headers.Authorization = `Bearer ${await getIdToken()}`;

  // Timeout explicite (2026-09-25) : `fetch()` seul n'a pas de limite — une requête bloquée
  // (serveur lent/injoignable) restait pendante indéfiniment côté UI au lieu d'échouer proprement.
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  let resp;
  try {
    resp = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(`apiService: ${method} ${path} a expiré après ${API_TIMEOUT_MS}ms.`);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
  if (resp.status === 404 && skipAuth) return null; // lecture publique (shared-deals) : absent = null, pas une erreur
  if (!resp.ok) {
    const text = await resp.text().catch(() => '');
    const error = new Error(`apiService: ${method} ${path} a échoué (${resp.status}) ${text}`);
    error.status = resp.status; // permet aux appelants de distinguer un cas précis (ex: 409 sur un achat déjà pris par un autre utilisateur, voir toggleDealPurchased)
    throw error;
  }
  if (resp.status === 204) return null;
  const contentType = resp.headers.get('content-type') || '';
  return contentType.includes('application/json') ? resp.json() : null;
}

/**
 * Ouvre un canal WebSocket authentifié et rappelle `onChange()` (sans argument — voir l'en-tête
 * de ce fichier) à chaque notification reçue après le "ready" initial. `onChange` n'est jamais
 * appelé pour le tout premier "ready" (accusé de réception transport, voir main.py : garantit
 * qu'aucune notification émise entre l'ouverture WS et l'enregistrement du LISTEN Postgres n'est
 * perdue — l'appelant a déjà sa donnée via le fetch initial fait en parallèle, voir
 * `onDealsIndexUpdate`). Retourne une fonction de nettoyage (même contrat que le retour d'un
 * `onSnapshot`).
 *
 * Reconnexion automatique (2026-09-25) : contrairement à `onSnapshot` (Firestore), un WebSocket
 * ne se rétablit jamais tout seul après une coupure (redémarrage de `guitarhunter-api-prod` à
 * chaque déploiement — `deploy.yml` —, coupure réseau/Tailscale). Backoff exponentiel
 * (`WS_RETRY_DELAY_MS` → `WS_RETRY_DELAY_MAX_MS`), réinitialisé dès qu'une connexion s'ouvre
 * pour de vrai (`onopen`), jeton Firebase redemandé à chaque tentative (peut avoir expiré entre
 * deux essais).
 *
 * Rafraîchissement après reconnexion (2026-09-26) : un changement survenu PENDANT la coupure
 * (ex: le fetch initial a échoué juste après un redémarrage serveur, ou une notification Postgres
 * manquée entre deux connexions) ne serait jamais rattrapé sinon — contrairement à `onSnapshot`,
 * qui redonne systématiquement un instantané complet après une reconnexion. Tout "ready" qui
 * suit le tout premier (donc reçu après une reconnexion réelle) déclenche désormais `onChange()`
 * comme une notification normale.
 *
 * Durcissements (2026-09-26, suite consultation Opus sur un "Failed to fetch" systématique) :
 * - Le backoff ne se réinitialise plus sur `onopen` (simple poignée de main TCP/WS) mais sur la
 *   réception du "ready" applicatif — seul signal qui prouve que le serveur a accepté la
 *   connexion ET terminé son `LISTEN` Postgres. Sinon, un socket qui s'ouvre puis se referme
 *   aussitôt (ex: Postgres indisponible côté serveur) fait boucler les tentatives à l'intervalle
 *   minimal au lieu de vraiment reculer.
 * - `onError` n'est plus rappelé à chaque tentative ratée (bruit inutile pendant un backoff qui
 *   fonctionne normalement) mais seulement après `ERROR_REPORT_THRESHOLD` échecs consécutifs,
 *   remis à zéro par un "ready" réussi.
 */
function openChangeSocket(path, onChange, onError) {
  const ERROR_REPORT_THRESHOLD = 3;
  let closed = false;
  let ws = null;
  let retryDelay = WS_RETRY_DELAY_MS;
  let hasConnectedOnce = false;
  let consecutiveFailures = 0;

  const scheduleRetry = () => {
    if (closed) return;
    const delay = retryDelay;
    retryDelay = Math.min(retryDelay * 2, WS_RETRY_DELAY_MAX_MS);
    setTimeout(connect, delay);
  };

  const reportError = (error) => {
    consecutiveFailures += 1;
    if (consecutiveFailures >= ERROR_REPORT_THRESHOLD) onError?.(error);
  };

  const connect = async () => {
    if (closed) return;
    try {
      const token = await getIdToken();
      if (closed) return;
      ws = new WebSocket(`${WS_BASE_URL}${path}?token=${encodeURIComponent(token)}`);
      ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'ready') {
          retryDelay = WS_RETRY_DELAY_MS;
          consecutiveFailures = 0;
          if (hasConnectedOnce) onChange(); // reconnexion : rattrape ce qui a pu être manqué pendant la coupure
          hasConnectedOnce = true;
          return;
        }
        onChange();
      };
      ws.onerror = () => reportError(new Error(`apiService: connexion WebSocket ${path} interrompue.`));
      ws.onclose = scheduleRetry; // couvre aussi bien une erreur (le close event suit) qu'un arrêt serveur propre
      if (closed) ws.close(); // fermé pendant l'ouverture asynchrone ci-dessus
    } catch (error) {
      reportError(error);
      scheduleRetry();
    }
  };
  connect();

  return () => {
    closed = true;
    ws?.close();
  };
}

// --- Reconstruction des formes camelCase / imbriquées (voir en-tête de ce fichier) -----------

// Champs `aiAnalysis` promus en colonnes propres côté Postgres (voir backend/deal_mapping.py::
// _AI_ANALYSIS_FIELDS) — restent en snake_case À L'INTÉRIEUR de `aiAnalysis`, comme côté
// Firestore (analyzer.py les produit déjà ainsi, jamais convertis en camelCase).
const AI_ANALYSIS_KEYS = [
  'verdict', 'classification', 'classification_rejected', 'brand', 'model_name',
  'production_year', 'country_of_origin', 'color', 'finish_application', 'finish_texture',
  'deal_score', 'authenticity_score', 'condition_score', 'liquidity_score',
  'restoration_interest_score', 'model_used', 'tier3_trigger',
];

// Duck-type d'un `firebase/firestore` Timestamp (`.seconds` + `.toDate()`) — Postgres renvoie soit
// une chaîne ISO (colonnes TIMESTAMPTZ, via la sérialisation JSON par défaut de FastAPI), soit un
// entier epoch-secondes (`published_at_ts`, voir schema.sql). Nécessaire car le reste du frontend
// consomme déjà les deux formes indifféremment sur un même objet deal (`.seconds` pour trier,
// `.toDate?.() ?? new Date(x)` pour afficher — voir `DealCard/utils.js::formatRelativeDate`).
function toFirestoreLikeTimestamp(value) {
  if (value == null) return null;
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return { seconds: Math.floor(date.getTime() / 1000), toDate: () => date };
}

function dealFromRow(row) {
  if (!row) return null;
  const aiAnalysis = { ...(row.ai_analysis_raw || {}) };
  AI_ANALYSIS_KEYS.forEach((key) => {
    if (row[key] !== undefined && row[key] !== null) aiAnalysis[key] = row[key];
  });
  // Rejet manuel ("pas intéressé") : préférence PERSONNELLE (`user_deal_state.is_rejected`,
  // catalogue partagé depuis le 2026-09-19) — ne touche plus `guitar_deals.status` côté base.
  // Synthétisé ici en `status: 'rejected'` + `aiAnalysis.verdict: 'REJECTED'` (même contrat que
  // l'ancien `firestoreService.js::rejectDeal`, qui écrivait les deux) pour que
  // `useDealsManager.js`/`DealsExplorer.jsx` continuent de filtrer sans modification.
  if (row.is_rejected) aiAnalysis.verdict = 'REJECTED';
  return {
    id: row.id,
    title: row.title,
    price: row.price,
    originalPrice: row.original_price,
    priceDropAmount: row.price_drop_amount,
    status: row.is_rejected ? 'rejected' : row.status,
    isFavorite: row.is_favorite,
    isPurchased: row.is_purchased,
    manualClassification: row.manual_classification,
    manualAnalysisOverrides: row.manual_analysis_overrides,
    link: row.link,
    location: row.location,
    latitude: row.latitude,
    longitude: row.longitude,
    publishedAtRaw: row.published_at_raw,
    imageUrls: row.image_urls,
    storageImageUrls: row.storage_image_urls,
    storageImageGsUris: row.storage_image_gs_uris,
    timestamp: toFirestoreLikeTimestamp(row.timestamp),
    soldTimestamp: toFirestoreLikeTimestamp(row.sold_at),
    publishTimestamp: toFirestoreLikeTimestamp(row.published_at_ts),
    purchasePrice: row.purchase_price,
    purchasedAt: toFirestoreLikeTimestamp(row.purchased_at),
    description: row.description,
    soldNotes: row.sold_notes,
    initialVerdict: row.initial_verdict,
    initialModelUsed: row.initial_model_used,
    aiAnalysis,
  };
}

function chatMessageFromRow(row) {
  return {
    id: row.id,
    role: row.role,
    parts: row.parts,
    displayText: row.display_text,
    attachedImagePartIndices: row.attached_image_part_indices ?? undefined,
    addedToGalleryUrls: row.added_to_gallery_urls ?? undefined,
    restorationProposals: row.restoration_proposals ?? undefined,
    photoRecall: row.photo_recall ?? undefined,
    isError: row.is_error,
    requalificationProposal: row.requalification_proposal ?? undefined,
    createdAt: row.created_at,
  };
}

function restorationItemFromRow(row) {
  return {
    id: row.id,
    label: row.label,
    category: row.category,
    status: row.status,
    source: row.source,
    createdAt: row.created_at,
    estimatedCost: row.estimated_cost ?? undefined,
    actualCost: row.actual_cost ?? undefined,
    notes: row.notes ?? undefined,
    proposedByMessageId: row.proposed_by_message_id ?? undefined,
    order: row.item_order ?? undefined,
    photoUrls: row.photo_urls ?? undefined,
    updatedAt: row.updated_at,
    completedAt: row.completed_at ?? undefined,
  };
}

function cityFromRow(row) {
  return {
    docId: row.id,
    id: row.id,
    name: row.name,
    latitude: row.latitude,
    longitude: row.longitude,
    needsReview: row.needs_review,
    isScannable: row.is_scannable,
    kijijiRadiusKm: row.kijiji_radius_km ?? undefined,
  };
}

// --- Annonces partagées publiquement (sans auth) ----------------------------------------------

export const createSharedDeal = async (deal) => {
  const ai = deal.aiAnalysis || {};
  const scores = {
    price_score: ai.price_score ?? null,
    condition_score: ai.condition_score ?? null,
    rareness_score: ai.rareness_score ?? null,
    demand_score: ai.demand_score ?? null,
    margin_score: ai.margin_score ?? null,
  };
  await apiFetch(`/shared-deals/${deal.id}`, {
    method: 'PUT',
    body: {
      title: deal.title || null,
      price: deal.price || null,
      location: deal.location || null,
      link: deal.link || null,
      description: deal.description || null,
      storageImageUrls: deal.storageImageUrls || [],
      imageUrls: deal.imageUrls || [],
      verdict: ai.verdict || deal.verdict || null,
      scores,
      analysis: ai.reasoning || ai.analysis || deal.analysis || null,
      tier3_summary: deal.tier3_summary || null,
      sharedAt: new Date().toISOString(),
    },
  });
};

export const getSharedDeal = async (dealId) => apiFetch(`/shared-deals/${dealId}`, { skipAuth: true });

// --- Bot Configuration --------------------------------------------------------------------

export const updateUserConfig = async (newConfig, _userId) => {
  const hasDotNotation = Object.keys(newConfig).some((k) => k.includes('.'));
  const patch = hasDotNotation ? unflatten(newConfig) : newConfig;
  try {
    await apiFetch('/users/me/config', { method: 'PATCH', body: patch });
    console.log("Config saved successfully.");
  } catch (error) {
    console.error("Error updating user config:", error);
    throw new Error("Erreur de sauvegarde de la configuration.");
  }
};

export const onBotConfigUpdate = (onUpdate, onError, _userId) => {
  const fetchAndEmit = async () => {
    try {
      const config = await apiFetch('/users/me/config');
      onUpdate(config);
    } catch (error) {
      console.error("Error fetching bot config:", error);
      onError({ message: "Dossier Python introuvable" });
    }
  };
  fetchAndEmit();
  return openChangeSocket('/ws/users/me/config', fetchAndEmit, onError);
};

// --- Commands ---

const addCommand = async (type, payload) => {
  try {
    return await apiFetch('/commands', { method: 'POST', body: { type, payload } });
  } catch (error) {
    console.error(`Error adding command ${type}:`, error);
    throw new Error("Erreur lors de l'envoi de la commande.");
  }
};

export const triggerManualRefresh = (_userId) => addCommand('REFRESH', null);
export const triggerManualCleanup = (_userId) => addCommand('CLEANUP', null);
export const triggerRelaunchAll = (_userId) => addCommand('REANALYZE_ALL', null);
// Rattrapage Chantier G (2026-09-19) : voir backend/bot.py::reevaluate_not_promoted.
export const triggerReevaluateNotPromoted = (_userId) => addCommand('REEVALUATE_NOT_PROMOTED', null);
export const triggerScanSpecificUrl = (url, _userId) => addCommand('SCAN_URL', url);
export const resetBotConfigToDefaults = (defaults, userId) => updateUserConfig(defaults, userId);
export const triggerStopBot = (_userId) => addCommand('STOP_BOT', null);
export const triggerStopScan = (_userId) => addCommand('STOP_SCAN', null);
export const triggerStartBot = (_userId) => addCommand('START_BOT', null);
export const requestClearLogs = (_userId) => addCommand('CLEAR_LOGS', null);

// Pas de canal temps réel dédié pour une commande individuelle (voir schema.sql — aucun trigger
// NOTIFY sur `commands`, le bot la traite en quelques secondes au plus) : poll léger de
// `GET /commands/{id}` jusqu'à sortie de `pending`, mêmes appels que le callback `onSnapshot`
// d'origine (callback(data) à chaque changement de statut observé).
export const onCommandUpdate = (commandId, callback, _userId) => {
  let cancelled = false;
  const poll = async () => {
    while (!cancelled) {
      try {
        const command = await apiFetch(`/commands/${commandId}`);
        if (cancelled) return;
        callback(command);
        if (command.status !== 'pending') return;
      } catch (error) {
        console.error(`Error polling command ${commandId}:`, error);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };
  poll();
  return () => { cancelled = true; };
};

// --- Deals ---

export const onDealsIndexUpdate = (onUpdate, onError, _userId) => {
  const fetchAndEmit = async () => {
    try {
      const rows = await apiFetch('/deals');
      const merged = {};
      rows.forEach((row) => { merged[row.id] = dealFromRow(row); });
      onUpdate(merged, rows.length);
    } catch (error) {
      console.error("Error listening to deals index:", error);
      onError(error);
    }
  };
  fetchAndEmit();
  return openChangeSocket('/ws/deals', fetchAndEmit, onError);
};

export const fetchDealsByIds = async (ids, _userId) => {
  if (!ids || ids.length === 0) return [];
  try {
    const rows = await apiFetch('/deals/by-ids', { method: 'POST', body: { ids } });
    return rows.map(dealFromRow);
  } catch (error) {
    console.error("Error fetching deals by IDs:", error);
    throw error;
  }
};

export const rejectDeal = async (dealId, _chunkId, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/reject`, { method: 'PATCH' });
  } catch (error) {
    console.error(`Error rejecting deal ${dealId}:`, error);
    throw new Error("Erreur lors du rejet de l'annonce.");
  }
};

export const deleteDeal = async (dealId, _chunkId, _userId) => {
  // Catalogue partagé (2026-09-19) : ne supprime plus l'annonce globale, seulement la
  // visibilité/les préférences de CET utilisateur (retrait de son fil) — transparent ici, même
  // contrat REST, voir backend/api/deals_repo.py::delete_deal.
  try {
    await apiFetch(`/deals/${dealId}`, { method: 'DELETE' });
  } catch (error) {
    console.error(`Error deleting deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'annonce.");
  }
};

export const retryDealAnalysis = (dealId, userId, userComment = '') =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: false, userComment });

export const forceExpertAnalysis = (dealId, userId, userComment = '') =>
  addCommand('ANALYZE_DEAL', { dealId, forceExpert: true, userComment });

export const toggleDealFavorite = async (dealId, _currentStatus, _chunkId, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/favorite`, { method: 'PATCH' });
  } catch (error) {
    console.error(`Error toggling favorite for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour des favoris.");
  }
};

export const toggleDealPurchased = async (dealId, currentStatus, _chunkId, _userId, purchasePrice = null) => {
  try {
    await apiFetch(`/deals/${dealId}/purchased`, {
      method: 'PATCH',
      body: !currentStatus ? { purchasePrice } : {},
    });
  } catch (error) {
    console.error(`Error toggling purchased for deal ${dealId}:`, error);
    // Achat GLOBAL (catalogue partagé, 2026-09-19) : 409 = un AUTRE utilisateur a acheté cette
    // annonce entre-temps — cas nouveau qui n'existait pas dans l'ancien schéma par utilisateur,
    // message dédié plutôt que l'erreur générique ci-dessous (voir main.py::patch_purchased).
    if (error.status === 409) {
      throw new Error("Cette annonce a déjà été achetée par un autre utilisateur.");
    }
    throw new Error("Erreur lors de la mise à jour du statut d'achat.");
  }
};

export const setDealClassification = async (dealId, _chunkId, _userId, classificationPath, _aiClassification = null) => {
  try {
    await apiFetch(`/deals/${dealId}/classification`, { method: 'PATCH', body: { classificationPath } });
  } catch (error) {
    console.error(`Error setting classification for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la correction de la catégorie.");
  }
};

// Remplace applyManualAnalysisOverrides — plus besoin de mettre à jour un index séparé en plus
// (voir backend/api/deals_repo.py::apply_manual_analysis_overrides, colonnes déjà indexées).
export const applyManualAnalysisOverrides = async (dealId, _chunkId, _userId, fields, _currentAnalysis) => {
  if (!fields || !Object.keys(fields).length) return;
  try {
    await apiFetch(`/deals/${dealId}/analysis-overrides`, { method: 'PATCH', body: fields });
  } catch (error) {
    console.error(`Error applying manual analysis overrides for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'application de la correction.");
  }
};

export const addImageToDealGallery = async (dealId, url, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/gallery`, { method: 'POST', body: { url } });
  } catch (error) {
    console.error(`Error adding gallery image for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de la photo à la galerie.");
  }
};

// --- Chat IA ---

export const onDealChatUpdate = (dealId, onUpdate, onError, _userId) => {
  const fetchAndEmit = async () => {
    try {
      const rows = await apiFetch(`/deals/${dealId}/chat`);
      onUpdate(rows.map(chatMessageFromRow));
    } catch (error) {
      console.error(`Error listening to chat for deal ${dealId}:`, error);
      onError?.(error);
    }
  };
  fetchAndEmit();
  return openChangeSocket(`/ws/deals/${dealId}/chat`, fetchAndEmit, onError);
};

export const addDealChatMessage = async (dealId, role, parts, displayText, _userId, attachedImagePartIndices, restorationProposals, photoRecall, isError, requalificationProposal) => {
  try {
    const result = await apiFetch(`/deals/${dealId}/chat`, {
      method: 'POST',
      body: {
        role, parts, displayText,
        attachedImagePartIndices: attachedImagePartIndices?.length ? attachedImagePartIndices : undefined,
        restorationProposals: restorationProposals?.length ? restorationProposals : undefined,
        photoRecall: photoRecall?.refs?.length ? photoRecall : undefined,
        isError: !!isError,
        requalificationProposal: requalificationProposal || undefined,
      },
    });
    return result.id;
  } catch (error) {
    console.error(`Error saving chat message for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la sauvegarde du message.");
  }
};

export const replaceDealChatMessage = async (dealId, messageId, { parts, displayText, restorationProposals, photoRecall, isError, requalificationProposal }, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/chat/${messageId}`, {
      method: 'PATCH',
      body: {
        parts, displayText,
        restorationProposals: restorationProposals?.length ? restorationProposals : null,
        photoRecall: photoRecall?.refs?.length ? photoRecall : null,
        isError: !!isError,
        requalificationProposal: requalificationProposal || null,
      },
    });
  } catch (error) {
    console.error(`Error replacing chat message ${messageId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour du message.");
  }
};

export const markChatMessageAddedToGallery = async (dealId, messageId, partIndex, url, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/chat/${messageId}/gallery`, { method: 'PATCH', body: { partIndex, url } });
  } catch (error) {
    console.error(`Error marking chat message ${messageId} as added to gallery:`, error);
    throw new Error("Erreur lors de la mise à jour du message.");
  }
};

export const markChatMessageRestorationProposalStatus = async (dealId, messageId, proposalIndex, status, _userId, itemId) => {
  try {
    await apiFetch(`/deals/${dealId}/chat/${messageId}/restoration-proposal`, {
      method: 'PATCH',
      body: { proposalIndex, status, itemId: itemId || undefined },
    });
  } catch (error) {
    console.error(`Error marking restoration proposal ${proposalIndex} on message ${messageId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la proposition.");
  }
};

export const markChatMessageRequalificationProposalStatus = async (dealId, messageId, status, _userId) => {
  try {
    await apiFetch(`/deals/${dealId}/chat/${messageId}/requalification-proposal`, {
      method: 'PATCH',
      body: { status },
    });
  } catch (error) {
    console.error(`Error marking requalification proposal on message ${messageId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la proposition.");
  }
};

// --- Plan de restauration ---

export const onRestorationPlanUpdate = (dealId, onUpdate, onError, _userId) => {
  const fetchAndEmit = async () => {
    try {
      const rows = await apiFetch(`/deals/${dealId}/restoration-plan`);
      onUpdate(rows.map(restorationItemFromRow));
    } catch (error) {
      console.error(`Error listening to restoration plan for deal ${dealId}:`, error);
      onError?.(error);
    }
  };
  fetchAndEmit();
  return openChangeSocket(`/ws/deals/${dealId}/restoration-plan`, fetchAndEmit, onError);
};

export const addRestorationItem = async (dealId, _userId, { label, category, estimatedCost, notes, source = 'user', proposedByMessageId, order }) => {
  try {
    const result = await apiFetch(`/deals/${dealId}/restoration-plan`, {
      method: 'POST',
      body: { label, category, estimatedCost, notes, source, proposedByMessageId, order },
    });
    return result.id;
  } catch (error) {
    console.error(`Error adding restoration item for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de l'étape de restauration.");
  }
};

export const updateRestorationItem = async (dealId, _userId, itemId, patch) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/${itemId}`, { method: 'PATCH', body: patch });
  } catch (error) {
    console.error(`Error updating restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la mise à jour de l'étape de restauration.");
  }
};

export const deleteRestorationItem = async (dealId, _userId, itemId) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/${itemId}`, { method: 'DELETE' });
  } catch (error) {
    console.error(`Error deleting restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la suppression de l'étape de restauration.");
  }
};

export const reorderRestorationItems = async (dealId, _userId, orderedItemIds) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/order`, { method: 'PATCH', body: { orderedItemIds } });
  } catch (error) {
    console.error(`Error reordering restoration items for deal ${dealId}:`, error);
    throw new Error("Erreur lors de la réorganisation des étapes.");
  }
};

export const backfillRestorationOrder = async (dealId, _userId, orderedItems) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/order`, {
      method: 'PATCH',
      body: { orderedItemIds: orderedItems.map((item) => item.id) },
    });
  } catch (error) {
    console.error(`Error backfilling restoration order for deal ${dealId}:`, error);
  }
};

export const addRestorationItemPhoto = async (dealId, _userId, itemId, url) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/${itemId}/photos`, { method: 'POST', body: { url } });
  } catch (error) {
    console.error(`Error adding photo to restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors de l'ajout de la photo à l'étape.");
  }
};

export const removeRestorationItemPhoto = async (dealId, _userId, itemId, url) => {
  try {
    await apiFetch(`/deals/${dealId}/restoration-plan/${itemId}/photos`, { method: 'DELETE', body: { url } });
  } catch (error) {
    console.error(`Error removing photo from restoration item ${itemId} for deal ${dealId}:`, error);
    throw new Error("Erreur lors du retrait de la photo de l'étape.");
  }
};

// --- Cities ---

export const onCitiesUpdate = (onUpdate, onError, _userId) => {
  const fetchAndEmit = async () => {
    try {
      const rows = await apiFetch('/cities');
      onUpdate(rows.map(cityFromRow).sort((a, b) => (a.name || '').localeCompare(b.name || '')));
    } catch (error) {
      console.error("Error listening to cities:", error);
      onError(error);
    }
  };
  fetchAndEmit();
  return openChangeSocket('/ws/cities', fetchAndEmit, onError);
};

export const requestAddCity = (cityPayload, _userId) => addCommand('ADD_CITY', cityPayload);

export const deleteCity = async (docId, _userId) => {
  try {
    await apiFetch(`/cities/${docId}/pref`, { method: 'DELETE' });
  } catch (error) {
    console.error(`Error removing city pref ${docId}:`, error);
    throw new Error("Erreur lors de la suppression de la ville.");
  }
};

export const toggleCityScannable = async (docId, _currentStatus, _userId) => {
  try {
    await apiFetch(`/cities/${docId}/scannable`, { method: 'PATCH' });
  } catch (error) {
    console.error(`Error toggling scannable for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour de la ville.");
  }
};

export const setCityKijijiRadius = async (docId, radiusKm, _userId) => {
  try {
    await apiFetch(`/cities/${docId}/kijiji-radius`, { method: 'PATCH', body: { radiusKm: radiusKm || null } });
  } catch (error) {
    console.error(`Error setting Kijiji radius for city ${docId}:`, error);
    throw new Error("Erreur lors de la mise à jour du rayon Kijiji.");
  }
};

// Chantier C-0 : instrumentation du coût chat pour cost_dashboard.py --from-db. Fire-and-forget
// (appelée sans await depuis useDealChat.js) — ne doit jamais faire échouer/ralentir le tour de
// chat en cours, donc avale ses propres erreurs plutôt que de les laisser remonter en rejet non géré.
export const recordLlmUsage = (usage) => {
  apiFetch('/usage', { method: 'POST', body: usage }).catch((error) => {
    console.error('Error recording LLM usage:', error);
  });
};
