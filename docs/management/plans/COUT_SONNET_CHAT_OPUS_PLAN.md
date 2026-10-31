# Plan — coût de Sonnet, instrument de coût du chat, option Opus (2026-10-31)

**Statut** : plan validé par l'utilisateur le 2026-10-31, rien de codé. Décision : **monitorer d'abord, optimiser ensuite** ; l'utilisateur doit d'abord se servir du chat.

## Constats (llm_usage, 30 jours au 2026-10-31)
- Expert Gemini : 36 appels (≈ 1 par jour), 10 700 tokens en entrée, 990 en sortie, 4,5 photos, ≈ 2 $ par mois. Sonnet 5.5 à 0,054 $ l'appel (rejeu) donnera le même ordre : l'optimiser rapporte au mieux ≈ 1 $ par mois.
- Chat Gemini : 26 tours, ≈ 4 100 tokens en entrée, 0 token en cache, dernier tour le 2026-10-13 ; peu utilisé.
- Le chat est déjà journalisé (`POST /usage` → `llm_usage`, `source='chat'`), mais `backend/api/usage_repo.py` écrit `provider='gemini'` en dur et le coût n'est lisible que dans `backend/scripts/cost_dashboard.py`, pas dans l'application.
- Aucun appel Claude en production avant le déploiement de `dae020c` (T3 Sonnet par défaut).

## Étapes
1. **Instrument de coût du chat (priorité)** : `provider` et `model` réels à l'enregistrement ; vue Administrateur (`/admin/*`) du coût du chat par jour, par utilisateur, par annonce, coût moyen d'une conversation ; prix d'Opus ajoutés à `PRICING` de `cost_dashboard.py`. Ne dépend pas du portage du chat en production.
2. **Option Opus** : bouton « demander à Opus » sur une annonce (réanalyse Expert avec `claude-opus-5-5`), désactivé par défaut, plafond de coût par jour ; chiffrer le prix par appel avant décision.
3. **Optimisation (plus tard, sur mesure réelle)** : d'abord le chat (cache, plan de restauration réinjecté à chaque tour, voir Chantier C de `COST_OPTIMIZATION_CHANTIERS.md`), une fois l'instrument en place et l'usage réel mesuré ; Expert Sonnet (effort, plafond d'image, `max_tokens`, TTL du cache) seulement si la facture dépasse nettement 2 $ par mois. Image, `max_tokens` et TTL se chiffrent sans rejeu ; seul l'effort exige un rejeu (5 à 6 annonces suffisent).
