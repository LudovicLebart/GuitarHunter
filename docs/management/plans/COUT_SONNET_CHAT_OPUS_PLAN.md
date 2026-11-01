# Plan — coût de Sonnet, instrument de coût du chat, option Opus (2026-10-31)

**Statut (2026-11-01)** : étape 1 (instrument de coût) codée (`f00c630`, `f047e60`) ; le portage du chat sur Claude est décidé et planifié ci-dessous, non codé. Décision : **monitorer d'abord, optimiser ensuite** ; l'utilisateur évite le chat parce qu'il le juge cher, donc les chiffres mesurés avant le correctif sous-estiment l'usage réel.

## Constats (llm_usage, 30 jours au 2026-10-31)
- Expert Gemini : 36 appels (≈ 1 par jour), 10 700 tokens en entrée, 990 en sortie, 4,5 photos, ≈ 2 $ par mois. Sonnet 5.5 à 0,054 $ l'appel (rejeu) donnera le même ordre : l'optimiser rapporte au mieux ≈ 1 $ par mois.
- Chat Gemini : 26 tours, ≈ 4 100 tokens en entrée, 0 token en cache, dernier tour le 2026-10-13 ; peu utilisé.
- Le chat est déjà journalisé (`POST /usage` → `llm_usage`, `source='chat'`), mais `backend/api/usage_repo.py` écrit `provider='gemini'` en dur et le coût n'est lisible que dans `backend/scripts/cost_dashboard.py`, pas dans l'application.
- Aucun appel Claude en production avant le déploiement de `dae020c` (T3 Sonnet par défaut).

## Décisions de l'utilisateur (2026-11-01)
- Le chat passe sur Claude **pour tout le monde**, **Sonnet 5.5 par défaut** ; réglage `analysisConfig.chatModel` (Gemini 3.1 Pro en secours).
- **Opus = consultation, pas bascule** : sur demande explicite (« consulte Opus » ou bouton), Sonnet rédige un dossier autonome (question à trancher, faits de l'annonce, acquis de la conversation, points incertains ; pas d'historique complet, pas de photo sauf si la question porte sur l'image, longueur maximale). Opus ne reçoit que ce dossier, sans outils, avec un plafond de réponse ; sa réponse apparaît dans le chat sous son nom avec son coût, et Sonnet la reçoit pour la suite. Le dossier est consultable (encadré replié). Estimation de coût affichée, sans confirmation.
- **Alerte à 2 $ par jour** (jamais de blocage), tous modèles confondus.

## Étapes
1. **Instrument de coût du chat (priorité) — FAIT le 2026-11-01** (voir le journal W44) : : `provider` et `model` réels à l'enregistrement ; vue Administrateur (`/admin/*`) du coût du chat par jour, par utilisateur, par annonce, coût moyen d'une conversation ; prix d'Opus ajoutés à `PRICING` de `cost_dashboard.py`. Ne dépend pas du portage du chat en production.
2. **Chat sur Claude, avec consultation d'Opus** : route serveur `POST /deals/{id}/chat/stream` (conversion des messages et photos au format Anthropic, cache de prompt, usage et `cache_write_tokens` enregistrés par le serveur, outils renvoyés au navigateur qui les exécute), adaptateur `claudeChatService.js` à l'interface de la session Gemini, réglage `chatModel` dans `ConfigPanel.jsx`, consultation d'Opus (dossier, plafond de réponse, coût affiché), mise en production (`ANTHROPIC_API_KEY` côté API, modules dans la liste de `deploy.yml`, tests au job `tests`), essai avec la conversation de l'angle du manche.
3. **Optimisation (plus tard, sur mesure réelle)** : d'abord le chat (cache, plan de restauration réinjecté à chaque tour, voir Chantier C de `COST_OPTIMIZATION_CHANTIERS.md`), une fois l'instrument en place et l'usage réel mesuré ; Expert Sonnet (effort, plafond d'image, `max_tokens`, TTL du cache) seulement si la facture dépasse nettement 2 $ par mois. Image, `max_tokens` et TTL se chiffrent sans rejeu ; seul l'effort exige un rejeu (5 à 6 annonces suffisent).
