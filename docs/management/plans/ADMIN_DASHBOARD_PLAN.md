# Plan d'Implémentation : Dashboard Administrateur

**Objectif :** Donner à l'administrateur une vue centralisée sur tous les utilisateurs de Guitar Hunter (activité, coût estimé, dernier login, statut du bot) et des actions de gestion (désactivation de compte, envoi de courriel, arrêt de bot à distance), sans exposer ces capacités aux utilisateurs normaux.

**Modèle IA Recommandé pour l'exécution :** `Gemini 2.5 Pro` (nouvelle surface d'autorisation admin + règles Firestore + refactor multi-fichiers backend/frontend).

**Stratégie :** Découpage en 2 phases pour limiter le risque — la lecture seule (monitoring) d'abord, les actions privilégiées (écriture/destructif) ensuite, validées séparément.

---

## Phase 1 — Monitoring (Lecture Seule)

### 1.1 Sécurité d'accès

Remplacer le check fragile actuel par email (`VITE_ADMIN_EMAIL`, utilisé aujourd'hui uniquement pour la migration one-shot dans `firestoreService.js`) par un **custom claim Firebase** `admin: true` :
- Script one-shot (Admin SDK, `backend/scripts/`) pour poser le claim sur le compte administrateur.
- Règles Firestore (`firestore.rules`) : autoriser la lecture cross-utilisateurs (`collectionGroup` sur `users` et `guitar_deals`) uniquement si `request.auth.token.admin == true`. Les règles d'isolation existantes (`request.auth.uid == userId`) restent inchangées pour tous les autres accès.

### 1.2 Composant `AdminDashboard.jsx`

Nouvelle vue frontend, montée uniquement si le claim admin est présent côté client (vérification défensive — la vraie protection reste les règles Firestore côté serveur). Colonnes par utilisateur :
- Email, UID, date de création, dernier login.
- `botStatus` actuel, villes actives, fréquence de scan configurée (`scanConfig.frequency`).

### 1.3 Coût / volume par utilisateur

Réutilise le modèle de coût déjà construit dans `backend/scripts/analyze_funnel_by_user.py` (`GEMINI_PROMPT_CACHING_PLAN.md §7`). **Décision d'architecture** : calculer côté **backend** et écrire périodiquement (ex: job `TaskScheduler` quotidien) dans un document `artifacts/{APP_ID}/admin_stats` plutôt que de faire lire au client des milliers de documents `guitar_deals` par utilisateur — plus scalable, cohérent avec le pattern déjà utilisé pour les stats du Dashboard.

---

## Phase 2 — Actions Privilégiées

### 2.1 Bus de commandes admin

Nouvelle collection `artifacts/{APP_ID}/admin_commands` (écriture restreinte à l'admin par les règles Firestore), traitée par `main.py` via Admin SDK — même pattern que le bus de commandes par utilisateur déjà en place (`ARCHITECTURE.md §1`), avec un `admin_command_handlers` dédié :

| Commande | Effet |
|---|---|
| `DISABLE_USER` | Désactivation **réversible** du compte Firebase Auth (`auth.update_user(uid, disabled=True)`). **Recommandé par défaut** — cohérent avec le pattern Soft Delete déjà utilisé pour les annonces vendues (`status: 'sold'`) plutôt qu'une suppression physique. |
| `SEND_EMAIL` | Réutilise le SMTP déjà configuré (`backend/notifications.py`) pour envoyer un message à un utilisateur. |
| `STOP_BOT` (admin) | La commande existe déjà par utilisateur (`ARCHITECTURE.md §1`) — simplement exposée dans le dashboard admin pour un accès direct sans que l'utilisateur ait à agir. |

**Suppression définitive de compte** : intentionnellement **non incluse par défaut** dans cette première version (destructrice et irréversible — Auth + Firestore + Storage). À ajouter seulement si explicitement demandé, avec un flux de confirmation à 2 étapes (type `handleRelaunchAll`).

### 2.2 Journal d'audit

Collection `artifacts/{APP_ID}/admin_audit_log` : qui a fait quoi, quand, sur quel utilisateur — indispensable dès qu'une action est irréversible ou impacte un tiers.

---

## Actions Supplémentaires Recommandées (à valider séparément)

- Ajustement à distance des quotas (`max_ads`, fréquence de scan) d'un utilisateur en cas d'abus ou de coût excessif.
- Vue agrégée quotidienne (volume total, coût total estimé, funnel global tous utilisateurs) — équivalent temps réel de `analyze_funnel_by_user.py` (§1.3).
- Accès en lecture aux logs/erreurs récents d'un utilisateur (collection `logs` déjà existante par utilisateur).

---

## Phase de Test et Migration

1. Poser le custom claim admin et déployer les règles Firestore mises à jour — vérifier qu'aucun utilisateur normal ne peut lire les données d'un autre (test de régression sécurité, critique).
2. Construire la Phase 1 (lecture seule) et la valider avant de commencer la Phase 2.
3. Phase 2 : tester `DISABLE_USER`/`SEND_EMAIL` sur un compte de test avant tout usage réel.
4. Documenter les résultats dans `docs/management/JOURNAL.md`.
