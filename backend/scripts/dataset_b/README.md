# Dataset B — collecte manuelle (mesures réelles)

Contexte complet : `docs/management/plans/NECK_RESET_VISION_PLAN.md` §4 étape 2, §5.
Fiches imprimables (protocole cale + prise de photo, grille de mesures) : `docs/assets/dataset_b_protocole/`.

## Workflow

1. Imprimer les 2 fiches (`docs/assets/dataset_b_protocole/`). Fiche 1 = protocole (réglage de cale —
   **cale côté tête = augmente l'action, simule le besoin de neck reset** — + les 5 vues soignées +
   3-5 photos "type annonce" en conditions non contrôlées, section C, **une seule série par
   guitare/séance, pas par configuration**). Fiche 2 = journal de session (une feuille par
   guitare/séance, une LIGNE par configuration testée) — pensée pour être remplie vite les mains
   occupées, pas recopiée fiche par fiche : transcrire tout le tableau en une seule fois dans les CSV
   en fin de séance.
2. Ranger les photos dans `photos/<guitare_id>/<config_id>/` (dossier non versionné, voir `.gitignore` —
   ce sont des fichiers personnels, pas du code).
3. Transcrire le tableau de la Fiche 2, en une fois, dans les 4 fichiers CSV de ce dossier :
   - `guitares.csv` — une ligne par guitare.
   - `configurations.csv` — une ligne par configuration (état initial ou cale testée) ; `position_cale`
     = `tete` (augmente l'action) ou `corps` (effet inverse) ; `relief_mm` mesuré une fois par séance.
   - `mesures.csv` — une ligne par configuration ; `projection_chevalet_mm` = règle droite posée sur
     les frettes, hauteur au-dessus du chevalet (remplace un angle en degrés, pas mesurable simplement).
   - `photos.csv` — une ligne par photo (`type_vue` = `ardoise`/`ensemble`/`sillet_chevalet`/
     `table_chevalet` [1 ligne par condition d'éclairage]/`12e_frette`/`profil`/`reglet_reference`/
     `type_annonce`), avec le chemin relatif vers `photos/`.
   (Chaque CSV contient 1-2 lignes d'exemple, préfixées `exemple_...` — à remplacer/supprimer.)
4. Relancer `python3 build_db.py` : reconstruit entièrement `dataset_b.sqlite` (non versionné, voir
   `.gitignore`) à partir des CSV. **Les CSV sont la source de vérité, pas la base** — c'est ce qui rend
   la mise à jour simple : éditer un tableur, relancer le script, la base est toujours à jour.

## Pourquoi une base SQLite si les CSV suffisent déjà ?

Les CSV restent lisibles/éditables à la main (Excel, Google Sheets, éditeur de texte). La base SQLite
sert pour la suite : requêtes jointes (ex. corréler une mesure d'action avec les métriques calculées à
partir des photos par le pipeline de vision, §4 étape 6 — jalon go/no-go), sans devoir réécrire cette
logique de jointure à chaque fois.
