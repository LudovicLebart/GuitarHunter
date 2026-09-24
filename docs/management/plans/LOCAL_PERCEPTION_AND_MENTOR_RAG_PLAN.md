# Plan — Réduction des coûts + Perception Locale + Mentor RAG Lutherie

**Date :** 2026-09-22 (v3 — réordonné sur l'objectif affiché : réduire les coûts)  
**Statut :** Brouillon à valider  
**Document complet :** [`docs/explanation/plan/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.pdf`](../../explanation/plan/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.pdf)

---

## 📋 Vue d'ensemble

Ce plan coordonne **4 chantiers parallèles** (C, I, V, M) visant à :

1. **Chantier C — Réduction des coûts** : dashboard de coût par poste (C-0), optimisation chat (C-1/C-2/C-3), migration Firestore vers Postgres (Chantier A).
2. **Chantier I étendu — Qwen local** : secours sans panne fournisseur, perception locale (description photo), portier spécialisé par distillation.
3. **Chantier V — RAG de valorisation** : injection de comparables réels dans le Tier 2 pour fiabiliser les estimations (fin de la "divination" de valeur).
4. **Chantier M — Mentor RAG lutherie** : augmentation du chat par annonce avec base de connaissances (réparation, specs, sécurité).

**Objectif primaire :** La facture. Chaque chantier est classé par ce qu'il rapporte en dollars ; ce qui n'en rapporte pas est dit tel quel (I et M = plaisir/apprentissage, pas coût).

---

## 🎯 Chantier C — Réduction des coûts

- **C-0** : Dashboard de coût par poste (T1 Qwen, T2, T3, chat, Firestore, Storage)  
- **C-1** : Chat allégé (1024px photos, résumé glissant historique, modèle moins cher par défaut)  
- **C-2** : Fin de l'observation miroir Flash-Lite  
- **C-3** : Optimisation Tier 3 (Pro-preview, seuil de déclenchement)  
- **C-4** : Chantier A (migration Postgres — 16–20 $/mois, tendance haussière)  
- **C-5** : Choix du fournisseur Tier 2 (Gemini 3.7 Flash vs alternativess, rejeu V-2)  

**Gain attendu :** Double chiffre par mois (le seul avec cet ordre de grandeur).

---

## 🧠 Chantier I — Qwen local

**Rôles possibles, par ordre d'engagement :**

1. **Secours** : chaîne T1 `qwen_cloud` → `qwen_local` → `gemini` (couvre panne TokenRouter, zéro entraînement).
2. **Perception** (Chantier B §8) : le local décrit les photos, les raisonneurs ne voient plus d'images (retire ~95 % de la vision des appels payants).
3. **Portier spécialisé** : fine-tuning du local pour T1 alone (seulement si 1 et 2 ont mesuré sa qualité).

**Phases :**
- **I-0** : Rejeu réel, 3 corrections avant lancement (VRAM, num_ctx fixé, métriques JSON).
- **I-1** : Secours (failover sur timeout/erreur réseau).
- **I-2** : Perception locale + test "texte seul" (3 semaines).
- **I-3/I-4** : Distillation (optionnel, si gain mesuré).

**Coût :** 1–3 $/mois (tokens d'images), sauf T2 si passe en local (I-4 — curiosité, pas un levier).

---

## 💰 Chantier V — RAG de valorisation

Le T2 produit actuellement `estimated_value` de mémoire → non auditable, péri

ssable, instable.  
**Solution :** Injection de **N comparables récents** (marque + modèle normalisé + titre, SQL + embeddings, sources internes + externes) dans le prompt du T2.

**Architecture hybride :**
- Filtre SQL : catégorie taxonomique, fenêtre de dates (18 mois), monnaie, exclusion rejets/doublons.
- Rapprochement sémantique : bge-m3 (CPU), similarité × récence × état, diversité des sources.
- Résultat : comparables + stats (médiane, P25–P75) + couverture.

**Phases :**
- **V-0** : Couverture (1 semaine, lecture seule, zéro appel IA) → décide où les sources externes sont indispensables.
- **V-1** : Index + récupération (2 semaines, SQLite + sqlite-vec).
- **V-2** : Rejeu T2 avec/sans comparables (1–2 semaines), **évaluation des fournisseurs T2** avant retour aux tarifs standard Gemini 01/01/2027.
- **V-3/V-4** : Ingestion sources externes (Reverb, détaillants, eBay) + bascule prod.

**Coût :** Neutre à légèrement positif (~0,2–0,6 $/annonce T2 à -1500–4000 tokens image, compensé si T2 passe Qwen).

---

## 👨‍🏫 Chantier M — Mentor RAG lutherie

Augmentation du chat par annonce avec base de connaissances : réparation, specs d'usine, histoire, points de vigilance.

**Corpus :**
1. Réparation/réglage (frets.com, StewMac, manuels constructeurs).
2. Specs par modèle (diapason, sillet, électronique, années/changements).
3. Histoire/généalogie (Wikidata/SPARQL, pages constructeurs).
4. Sécurité (10–20 fiches manuelles : truss rod, colles, finition).
5. Expérience propre (plans de restauration terminés).

**Intégration :** RAG côté backend (recherche + injection prompt), outil `search_lutherie_docs` côté chat (Firebase AI Logic).

**Phases :**
- **M0** : Prototype CLI (indexer frets.com + manuels, 20 questions réelles).
- **M1** : Intégration chat (2 semaines, bus de commandes Firestore).
- **M2** : Plan de restauration augmenté (1–2 semaines, contexte du plan injecté).
- **M3** : Fiche instrument (1–2 semaines, générée à achat).

**Coût :** 600–900 tokens d'extraits par message (pure ajout, aucun levier économique). **Accepté comme coût de plaisir/apprentissage** si chat allégé par C-1.

---

## 📅 Ordonnancement

| Semaine | Tâches |
|---------|--------|
| 1 | **C-0** (dashboard), **I-0** (rejeu Qwen), **V-0** (couverture) |
| 2 | **C-1** (chat 1024px + résumé), **I-1** (secours), **V-1** (index) |
| 3 | **C-1/C-2/C-3** (modèle par défaut, fin miroir, T3) |
| 4–5 | **Contrat perception**, **I-2** (hybrid test), **V-2** (rejeu T2 + choix fournisseur avant 01/01/2027) |
| 6–8 | **I-2 shadow/bascule**, **V-3/V-4**, **M0–M1** sur chat allégé |
| Ensuite | **I-3/I-4** (si envie), **M2–M3** |

**Chaque semaine :** relire C-0 dashboard avant d'attaquer la ligne suivante.

---

## 🚨 Décisions à prendre

0. **C-0 avant tout** : construire la ventilation de la facture par poste, puis seulement choisir la ligne.
0b. **Le mentor (M) est-il accepté comme coût de plaisir**, à construire sur le chat déjà allégé (C-1) ?
1. **Lancer I-0** avec les trois corrections ou tel quel ? (Recommandation : corrigé).
2. **Le rôle secours (I-1) est-il un objectif** en soi ? (Recommandation : oui, seul indépendant de la qualité du local).
3. **Rejeu du candidat hybrid** avant toute décision sur la perception.
4. **M1 et V** : bus de commandes Firestore ou attendre l'API Postgres en prod ?
5. **Jeu d'éval permanent** (§2.7) : quelles actions comptent comme « pépite confirmée » ?
6. **Sources externes V** : conditions d'utilisation de Reverb, détaillants, eBay ?

---

## 🔗 Références

- **Instrumentation coûts :** `backend/scripts/cost_dashboard.py`, `[tokens]` logs dans LogViewer.
- **Chantier C-0 (validé)** : voir `TODO.md` section "💸 Optimisation coûts Gemini API".
- **Chantier I (Qwen)** : voir `TODO.md` section (rechercher "Chantier I").
- **Chantier V (Valorisation)** : voir `TODO.md` section (rechercher "RAG").
- **Chantier M (Mentor)** : voir `TODO.md` section (rechercher "Mentor").
- **Migration Postgres** : `docs/management/plans/FIRESTORE_MIGRATION_PLAN.md` (Chantier A, précondition).

---

> 📄 **Document complet** : [`docs/explanation/plan/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.pdf`](../../explanation/plan/LOCAL_PERCEPTION_AND_MENTOR_RAG_PLAN.pdf)  
> *Pour le détail complet de chaque chantier, phases, risques et métriques, voir le PDF ci-dessus.*
