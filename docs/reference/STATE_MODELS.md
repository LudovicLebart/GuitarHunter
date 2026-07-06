# Modèles de Données - Guitar Hunter

Ce document définit les contrats d'interface pour les objets échangés via Firestore entre le Backend Python et le Frontend React.

## 1. Objet "Commande" (Command)
Les commandes sont créées par le Frontend pour demander des actions asynchrones au Bot.

**Collection** : `artifacts/{APP_ID}/users/{USER_ID}/commands/`

```typescript
interface Command {
  /** Type de l'action à exécuter */
  type: 'REFRESH' | 'CLEANUP' | 'REANALYZE_ALL' | 'SCAN_URL' | 'ADD_CITY' | 'ANALYZE_DEAL' | 'CLEAR_LOGS' | 'STOP_BOT' | 'STOP_SCAN' | 'START_BOT';
  
  /** Données nécessaires à la commande (dépend du type) */
  payload: any | null; 
  // Exemples : 
  // - string (URL pour SCAN_URL, nom de ville pour ADD_CITY)
  // - { dealId: string, forceExpert: boolean } (pour ANALYZE_DEAL)
  
  /** État de traitement par le backend */
  status: 'pending' | 'completed' | 'failed';
  
  /** Date de création (Firestore Server Timestamp) */
  createdAt: Timestamp;
}
```

---

## 2. Objet "Deal" (Annonce)
Les "Deals" sont créés/mis à jour par le Backend après analyse et consommés par le Frontend.

**Collection** : `artifacts/{APP_ID}/users/{USER_ID}/guitar_deals/`

```typescript
interface Deal {
  /** Identifiant unique de l'annonce (souvent l'ID Facebook) */
  id: string; // Obligatoire

  /** Informations de base (provenant du scraper) */
  title: string;       // Obligatoire
  price: number;       // Obligatoire
  link: string;        // Obligatoire (URL Facebook)
  description?: string; // Optionnel
  location: string;    // Obligatoire (Ville)
  imageUrl?: string;   // Optionnel (Image principale)
  imageUrls?: string[]; // Optionnel (Galerie)
  
  /** Métadonnées géographiques (si disponibles) */
  latitude?: number;   // Optionnel
  longitude?: number;  // Optionnel

  /** État de l'annonce dans le flux */
  status: 'active' | 'rejected' | 'sold' | 'analyzing' | 'analyzing_expert' | 'analysis_failed';
  
  /** Marqueur de favoris (géré par le Frontend) */
  isFavorite: boolean; // Obligatoire (default: false)

  /** Résultat de l'analyse IA (Gemini) */
  aiAnalysis: {
    /** Verdict final court */
    verdict: 'PEPITE' | 'FAST_FLIP' | 'LUTHIER_PROJ' | 'CASE_WIN' | 'COLLECTION' | 
             'BAD_DEAL' | 'REJECTED_ITEM' | 'REJECTED_SERVICE' | 'INCOMPLETE_DATA' | 
             'ERROR' | 'PENDING';
    
    /** Argumentaire détaillé de l'IA */
    reasoning: string; // Obligatoire si verdict !== 'PENDING'
    
    /** Classification taxonomique (ex: "Electric Guitars > Solid Body") */
    classification?: string; // Optionnel
    
    /** Nom du modèle IA ayant produit le résultat final */
    model_used?: string; // Optionnel

    /** Double appartenance (2026-07-06) : true si le verdict est FAST_FLIP/LUTHIER_PROJ/CASE_WIN/COLLECTION
        ET que les critères PEPITE sont AUSSI remplis. L'annonce apparaît alors aussi dans le filtre/notifs Pépites. */
    also_qualifies_pepite?: boolean; // Optionnel (absent = false)

    /** Indices numériques (0-10) ajoutés en Session 18 */
    deal_score?: number;
    authenticity_score?: number;
    condition_score?: number;
    liquidity_score?: number;
    restoration_interest_score?: number;
  };

  /** Horodatage de détection de vente */
  soldAt?: Timestamp; // Optionnel

  /** Horodatage de dernière mise à jour */
  timestamp: Timestamp; // Obligatoire
}
```

### Notes sur les types
- **Timestamp** : Objet Firestore contenant `seconds` et `nanoseconds`.
- **Status (Deal)** : Le statut `analyzing` et `analyzing_expert` est souvent positionné de manière éphémère par le Frontend juste avant d'envoyer la commande `ANALYZE_DEAL`.
- **Verdict** : Les verdicts "Legacy" (ex: `REJECTED`, `GOOD_DEAL`) peuvent encore exister dans la base mais sont progressivement remplacés par la nouvelle nomenclature.
- **Terminology Shift** : Suite à l'expansion aux amplis et étuis (Session 20), le système utilise désormais `ancillary_value` (auparavant `estimated_case_value`) et `net_item_cost` (auparavant `net_guitar_cost`) pour refléter une approche multi-produit.
