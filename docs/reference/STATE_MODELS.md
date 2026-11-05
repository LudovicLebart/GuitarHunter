# Modèles de données — contrats d'interface

> Réécrit le 2026-11-05 (passe « deepdocument », section 1). L'ancienne version décrivait des documents Firestore ; ils n'existent plus. **Le schéma réel est dans [`donnees.md`](donnees.md)**. Ce fichier ne garde que la forme des objets tels que le Frontend les manipule, avec leur correspondance en base.

## Commande (`commands`)

Créée par `POST /commands`, lue et exécutée par le bot (accès SQL direct).

```typescript
interface Command {
  id: number;
  type: 'REFRESH' | 'CLEANUP' | 'REANALYZE_ALL' | 'SCAN_URL' | 'ADD_CITY' | 'ANALYZE_DEAL'
      | 'REEVALUATE_NOT_PROMOTED' | 'CLEAR_LOGS' | 'STOP_BOT' | 'STOP_SCAN' | 'START_BOT';
  payload: any | null;        // JSONB ; chaîne (URL pour SCAN_URL, nom de ville pour ADD_CITY) ou objet
  status: 'pending' | 'completed' | 'failed';
  error_message?: string;
  created_at: string;
  completed_at?: string;
}
```

Types relevés dans la table de dispatch de `main.py`. `ADD_CITY` accepte une chaîne (repli) ou `{name, latitude, longitude, region_hint}`. `ANALYZE_DEAL` : `{dealId, forceExpert, userComment}` (`bot.py::analyze_single_deal` ; `dealId` obligatoire, les deux autres optionnels).

## Annonce (`guitar_deals`, vue par utilisateur)

Les colonnes sont en snake_case en base ; la fonction de mappage de `src/services/apiService.js` (ligne ≈ 318 à 366) construit l'objet de l'interface. La liste complète des colonnes est dans `donnees.md`. Forme exposée au front :

- **Identité** : `id`, `title`, `price`, `originalPrice`, `priceDropAmount`, `link`, `location`, `latitude`, `longitude`, `publishedAtRaw`, `description` (absente de l'index), `imageUrls`, `storageImageUrls`, `storageImageGsUris`.
- **Cycle de vie** : `status`, `timestamp` (dernière modification), `soldTimestamp` (colonne `sold_at`), `publishTimestamp` (colonne `published_at_ts`), `soldNotes`. Les dates sont converties au format `{seconds, nanoseconds}` hérité de Firestore (`toFirestoreLikeTimestamp`).
- **Analyse, sous `aiAnalysis`** (en snake_case, comme en base) : le contenu de `ai_analysis_raw` (texte `reasoning` compris, fiche complète seulement), recouvert par les colonnes promues (`verdict`, `classification`, `brand`, `model_name`, `production_year`, `country_of_origin`, `color`, les cinq scores 0 à 10, `model_used`, `also_qualifies_pepite`, `estimated_gross_margin`…) quand elles ne sont pas nulles, plus `gatekeeperVerdict`.
- **Propre à l'utilisateur** : `isFavorite` et le rejet manuel (table `user_deal_state`, jamais sur l'annonce partagée). **Un rejet manuel est synthétisé côté front** : `status = 'rejected'` et `aiAnalysis.verdict = 'REJECTED'`, sans rien changer en base sur l'annonce.
- **Achat** (fait global) : `isPurchased`, `purchasedByUserId`, `purchasePrice`, `purchasedAt`, `userSalePrice`, `userSoldAt`, `restorationSpent` (calculé à la lecture, acheteur seulement).
- **Corrections manuelles** : `manualClassification` prime sur la classification de l'IA ; `manualAnalysisOverrides` contient les corrections des autres champs et survit aux ré-analyses. `initialVerdict`, `initialModelUsed`.

### Verdicts

| Verdict | Sens |
|---|---|
| `PEPITE`, `FAST_FLIP`, `LUTHIER_PROJ`, `CASE_WIN`, `COLLECTION` | Opportunités. Les quatre derniers peuvent aussi porter `also_qualifies_pepite` (double appartenance) |
| `FAIR` | Prix correct, pas une opportunité. Verdict du Portier : **n'est pas un rejet**, l'annonce continue vers l'Analyste |
| `BAD_DEAL` | Prix jugé excessif par l'IA. Garde `status = 'analyzed'`, masqué par `ARCHIVE_GROUP`. Verdict du Portier = rejet : l'annonce n'atteint pas l'Analyste |
| `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA` | Rejets de fond |
| `NOT_PROMOTED` | A passé le Portier mais sa famille n'est pas dans la Recherche Active ; arrêtée avant l'Analyste, conservée pour être repromue. Si `gatekeeper_verdict` vaut `PEPITE`, la carte garde le badge Pépite (« Hors recherche ») |
| `REJECTED` | Rejet par mot-clé d'exclusion (écrit par le bot avec `status = 'rejected'`) et rejet manuel de l'utilisateur (synthétisé côté front) |
| `GOOD_DEAL` | Hérité (ancienne nomenclature), encore affiché |
| `ERROR`, `PENDING` | États d'échec ou d'attente |

`ARCHIVE_GROUP` (`src/constants.js`) = `BAD_DEAL`, `REJECTED_ITEM`, `REJECTED_SERVICE`, `INCOMPLETE_DATA`, `REJECTED`, `SOLD`, `NOT_PROMOTED`.

`initial_verdict` conserve le verdict du tout premier passage. Une analyse forcée écrase `ai_analysis_raw.gatekeeperVerdict` par `MANUAL_RETRY` : le verdict d'origine du Portier se lit alors dans `initial_verdict`.

## Notes
- Les horodatages sont des chaînes ISO (`TIMESTAMPTZ` en base) ; `published_at_ts` est un entier (epoch en secondes).
- Depuis l'extension aux amplis et étuis, les champs de coût utilisent `ancillary_value` et `net_item_cost` (anciennement `estimated_case_value` et `net_guitar_cost`).
- Le chat et le plan de restauration ont leurs propres tables (`deal_chat`, `restoration_plan_items`) ; leurs champs sont décrits dans `donnees.md`, leur logique dans `DATA_FLOW.md` §5.1 et §5.2.
