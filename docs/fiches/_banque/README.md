# Banque d'éléments SVG pour les fiches

Les fiches doivent être **illustrées** (voir `../README.md`). Ce dossier regroupe de quoi fabriquer des schémas au **même style**, sans droits à gérer : tout est dessiné ici.

- `kit.py` : les éléments (fonctions Python qui renvoient du SVG) et la palette commune.
- `build_<sujet>.py` : un petit script par schéma, qui assemble des éléments et écrit le `.svg` dans `docs/fiches/img/<slug>/`. Exemple : `build_retrouver_humidite.py`.
- Les images des fiches restent de simples fichiers `.svg` : le site n'exécute rien. Ce dossier (préfixé `_`) n'est ni chargé en base ni copié au site.

## Éléments disponibles (`kit.py`)

| Fonction | Dessine |
|---|---|
| `svg(largeur, hauteur, titre, description, corps)` | Fichier complet (fond clair, `<title>` et `<desc>` pour l'accessibilité) |
| `guitare_dessus(x, y, echelle)` | Guitare acoustique à plat : corps galbé, rosace, chevalet, manche, tête et mécaniques (tête à droite) |
| `coupe_table(x, y, largeur, epaisseur)` | Coupe d'une portion de table, avec vernis |
| `sac(x, y, largeur, hauteur, etiquette)` | Sac plastique fermé |
| `bol_eponge(x, y)` | Bol d'eau, éponge et vapeur |
| `hygrometre(x, y)` | Hygromètre (cadran, zone verte, aiguille) |
| `ruban(x, y)`, `coton_tige(x, y)` | Ruban de masquage, coton-tige |
| `repere(n, x, y, legende)` | Pastille numérotée 1, 2, 3… avec légende |
| `fleche(x1, y1, x2, y2)` | Flèche droite |
| `bon_mauvais(x, y, bon)` | Pastille ✓ vert ou ✗ rouge |
| `texte(x, y, t, ...)` | Texte aligné |
| `boite(x, y, l, h, titre, sous_titre)` | Case d'organigramme (étape, arrêt) |
| `manche_profil(x, y, longueur, relief)` | Manche vu de côté, frettes aux vraies proportions, creux réglable |
| `frette_corde(x, y, hauteur)` | Zoom sur une frette avec la corde au-dessus (action) |
| `ecrou_rotation(x, y, sens)` | Écrou de truss rod avec flèche horaire ou antihoraire |
| `cote(x1, y1, x2, y2)`, `rappel(...)` | Cote à deux pointes (`dehors=True` si elle est trop courte) et ligne de rappel pointillée |
| `etiquette(n, x, y, cx, cy)` | Repère numéroté relié par un trait à l'élément qu'il désigne : aucun repère ne flotte |
| `ecrire(slug, nom, l, h, titre, desc, morceaux)` | Écrit le `.svg` dans `img/<slug>/` : tous les `build_*.py` passent par là |

## Coupe latérale commune (`coupe.py`)

Les schémas de la série « neck reset » montrent tous la même vue : manche à gauche, corps à droite. Cette vue est dessinée **une seule fois**, dans `coupe.py` : `Coupe(angle=…)` fournit le corps (table, rosace, tasseau, vide au fond de la queue d'aronde, fond, éclisse), le chevalet et son sillet, le manche (touche, frettes, talon, queue d'aronde, rallonge de touche), la fente de la 15e frette et le coin à retirer du talon. L'angle du manche tourne autour du point P ; les points d'ancrage (`c.P`, `c.selle`, `c.pt(u, v)`) servent aux annotations. Un nouveau schéma de la série **n'en redessine rien** : il crée une `Coupe` et ajoute ses cotes, flèches et outils. Si un élément de la coupe manque (par exemple une cale de manche vissé), l'ajouter à `coupe.py` pour que toutes les fiches le partagent.

Tout nouvel élément utile à plusieurs fiches (sillet, truss rod, touche, barrage, serre-joint…) s'ajoute **ici** plutôt que dans un schéma isolé.

## Règles de style

- **Fond clair** (`#f8fafc`) : les images s'affichent sur le thème sombre du site, elles portent leur propre fond.
- **Palette** : celle de `kit.py` (`C`) ; bois clair, manche brun, bleu pour l'eau, vert = bon, rouge = mauvais.
- **Repères numérotés** pour suivre l'ordre des étapes ; une légende courte par repère ; une phrase d'explication en bas du schéma.
- **Lisible en petit** : texte de 13 px minimum dans le fichier (viewBox 820 de large), pas de chevauchement entre un texte et un dessin.
- Un schéma montre **le geste, le sens, l'orientation ou la différence entre bon et mauvais**, jamais de décoration.
- **Vérifier à l'œil** : ouvrir le `.svg` dans un navigateur avant de le référencer dans une fiche.
- Nom du fichier : `NN-description.svg`, référencé en chemin relatif depuis la fiche : `![légende](img/<slug>/01-nom.svg)`.

## Ajouter ou modifier un schéma

1. Écrire (ou ouvrir) `build_<sujet>.py`, assembler les éléments, lancer `python docs/fiches/_banque/build_<sujet>.py`.
2. Regarder le résultat, ajuster, relancer.
3. Référencer l'image dans l'étape qu'elle sert ; ajouter une ligne à l'historique de la fiche.

Scripts : `build_retrouver_humidite.py` (sac et hygromètre), `build_reglage.py` (ordre des réglages, sillet, action, relief, truss rod, déblocage), `build_neck_reset_colle.py` (série neck reset, sur `coupe.py`). `build_decoller_touche.py` et `build_cale_rallonge.py` ont encore leur propre petite coupe locale : à ramener sur `coupe.py` quand on les retouchera.

Les trois premiers schémas de la fiche « Réparer une fissure dans la table » et celui de « Nettoyer avant collage » sont encore des fichiers dessinés à la main : à reconstruire avec la banque quand on les retouchera.
