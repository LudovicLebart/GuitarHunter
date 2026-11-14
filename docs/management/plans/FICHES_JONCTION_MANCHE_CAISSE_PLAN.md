# Plan — fiches « jonction manche/caisse décollée » (talon, éclisses, bloc de manche)

**Date** : 2026-11-14 · **Statut** : plan proposé, rien de rédigé · **Origine** : réparation en cours d'une guitare acoustique (Fender Tim Armstrong Hellcat) dont le talon se décolle d'une éclisse, l'autre éclisse s'ouvrant un peu, le manche ne reprenant plus exactement sa place. Avis de luthier-conseil obtenu (Opus) ; **les sources ne sont pas encore vérifiées** et l'avis reste à confirmer par un luthier avant de passer une fiche en `validee`.

## 1. Constat (d'après photos, à confirmer)

- Construction de **guitare acoustique à table plate** : bloc de manche entre table et dos, contre-éclisses crantées, probable queue d'aronde (pièce trapézoïdale visible sur le bloc). Les fiches doivent être écrites pour l'acoustique ; une variante demi-caisse seulement si un cas réel l'exige.
- Le talon, le liseré du dos et l'éclisse sont décalés ; les traces noires découvertes sur le liseré donnent l'empreinte de l'ancienne position.
- Une ligne sur le vernis près de la jonction pourrait être une fissure de table : à inspecter de l'intérieur avant toute tension.
- **Ce que les photos ne tranchent pas** : la queue d'aronde a-t-elle du jeu, ou est-ce le bloc qui a décollé des éclisses/du dos ? Cela décide de la réparation.

## 2. Diagnostic (test décisif)

Témoins au crayon qui traversent chaque joint (talon/éclisse, liseré du dos, trapèze → bloc, bloc → dos), photo de référence, puis accordage un ton plus bas 10-15 minutes et nouvelle photo : le trait qui se casse désigne le joint qui travaille. Compléter par : humidité (45-50 %), lampe dans la caisse, miroir/endoscope, cales d'épaisseur à trois hauteurs cordes détendues puis tendues, règle sur les frettes, mesure de la bande de liseré découverte.

## 3. Branches de réparation

1. **Queue d'aronde saine, bloc/éclisses/dos décollés** : nettoyer, serrer à blanc (si le désalignement ne disparaît pas à blanc, ne pas le forcer), recoller à la colle aliphatique (ou colle de peau liquide fraîche), attendre 24-48 h avant la tension.
2. **Queue d'aronde lâche** : dépose du manche, regarnissage des joues, recollage à la colle de peau ; ou conversion en manche vissé. Ne jamais injecter de colle dans une queue d'aronde lâche sans dépose, ni époxy dans ce joint.
3. **Table fendue au bord du bloc** : réparer la table d'abord.

Ordre global : humidité → diagnostic → avis du luthier → table → joints intérieurs → manche → talon/éclisse → liseré → tension progressive → surveillance 2-4 semaines → réglages → retouche du fini noir en dernier.

## 4. Fiches à créer

Existant à réutiliser par renvoi : `retrouver-humidite-normale`, `nettoyer-avant-collage`, `refaire-angle-du-manche`, `decoller-la-touche`, `caler-la-rallonge-de-touche`, `reparation-fissure-table`, `mesurer-relief-manche`, `reglage-action`.

| P | Slug | Titre | Catégorie | Diff. | Durée | Notes |
|---|------|-------|-----------|:-----:|-------|-------|
| 1 | `diagnostiquer-joint-manche-caisse` | Diagnostiquer un talon ou une éclisse qui se décolle | Structurel | 2/5 | 1 h + 24-48 h | Fiche maîtresse, arbre de décision, tests ci-dessus |
| 1 | `choisir-sa-colle` | Choisir sa colle : peau, aliphatique, époxy, cyanoacrylate | Autre | 1/5 | 15 min | Évite de répéter le tableau dans chaque fiche de collage |
| 1 | `recoller-eclisse-dos` | Recoller un joint dos/éclisse ou table/éclisse ouvert | Structurel | 3/5 | 1-2 h + 24 h | Bois massif et contreplaqué ; cales profilées, pinces de bord |
| 2 | `recoller-bloc-de-manche` | Recoller un bloc de manche décollé | Structurel | 4/5 | 2 h + 24 h | Serrage par la rosace, cales attachées |
| 2 | `recoller-un-liseret` | Recoller un liseré et nettoyer ses traces | Cosmétique | 2/5 | 1 h | Test ABS/celluloïd, ruban tendu |
| 2 | `retoucher-un-vernis-noir` | Retoucher un éclat de vernis noir | Cosmétique | 3/5 | 2 h + séchage | S'entraîner sur une planchette |
| 3 | `deposer-manche-colle` | Déposer un manche collé (vapeur/chaleur) | Structurel | 5/5 | demi-journée | Remplace « Neck reset d'un manche collé » des fiches envisagées |
| 3 | `regarnir-queue-d-aronde` | Regarnir et recoller une queue d'aronde | Structurel | 4/5 | — | Suite de la dépose |
| 3 | `convertir-manche-colle-en-visse` | Convertir un manche collé en vissé | Structurel | 4/5 | — | Déjà envisagée ; alternative économique |
| 3 | `fabriquer-cales-de-serrage` | Fabriquer des cales profilées | Autre | 2/5 | 1 h | Optionnelle : d'abord intégrée à `recoller-bloc-de-manche` |

Fusionnée d'abord dans la fiche de diagnostic (sortir seulement si une 3e fiche en a besoin) : inspection intérieure (miroir, endoscope, lampe).

**Modifications d'existant** : élargir `nettoyer-avant-collage` aux joints (alias « nettoyer un joint avant recollage ») ; ajouter à `refaire-angle-du-manche` (« Reconnaître le cas ») le symptôme « talon qui s'ouvre côté dos » avec renvoi vers la fiche de diagnostic ; mettre à jour la section « Fiches envisagées » du README.

## 5. Contraintes de rédaction (rappel du README des fiches)

- Gabarit `_GABARIT.md`, en-tête YAML complet, statut `brouillon`, `## Historique des révisions` en dernière section.
- **Images obligatoires** : schémas SVG originaux avec la banque `_banque/` (ex. coupe latérale avec interfaces numérotées, rotation du manche, témoins au crayon, cales aux 3 hauteurs, arbre de décision, serrage par la rosace). Aucune image copiée sans accord ; les photos de la réparation peuvent servir une fois anonymisées.
- **Sources vérifiées** avant rédaction (pistes non vérifiées : frets.com, StewMac « Trade Secrets », Haze Guitars) ; signaler les divergences (colle de peau ou aliphatique pour les joints secondaires).
- Dépôt public : aucune donnée personnelle, aucun prix d'achat, aucun titre ou lien d'annonce.
- Validation : `python backend/scripts/seed_guitar_fiches.py --dry-run`, puis `npm test`.

## 6. Étapes proposées

1. Valider ce plan (et l'ordre de priorité).
2. Faire le diagnostic sur la guitare (tests T0 à T8) : le résultat dit quelles fiches de priorité 1-2 sont utiles tout de suite ; la branche 2 (priorité 3) ne sera écrite que si elle est nécessaire.
3. Rédiger les fiches de priorité 1 au fil de la réparation, en documentant par des photos ; passage en `en_revision` puis `validee` après la réparation et, si besoin, relecture par le luthier.
4. Étape 3 du protocole du projet (journal, TODO, index README) à la validation.
