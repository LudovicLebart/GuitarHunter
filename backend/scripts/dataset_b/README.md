# Dataset B — collecte manuelle (mesures réelles)

Contexte complet : `docs/management/plans/NECK_RESET_VISION_PLAN.md` §4 étape 2, §5.
Fiches imprimables (protocole cale + prise de photo, grille de mesures) : `docs/assets/dataset_b_protocole/`.

## Workflow

1. Imprimer les 2 fiches (`docs/assets/dataset_b_protocole/`), suivre le protocole pour chaque configuration
   (état initial, puis chaque épaisseur de cale testée).
2. Ranger les photos dans `photos/<guitare_id>/<config_id>/` (dossier non versionné, voir `.gitignore` —
   ce sont des fichiers personnels, pas du code).
3. Reporter les fiches papier dans les 4 fichiers CSV de ce dossier :
   - `guitares.csv` — une ligne par guitare.
   - `configurations.csv` — une ligne par configuration (état initial ou cale testée).
   - `mesures.csv` — une ligne par configuration, les valeurs de la grille de mesures.
   - `photos.csv` — une ligne par photo, avec le chemin relatif vers `photos/`.
   (Chaque CSV contient 1-2 lignes d'exemple, préfixées `exemple_...` — à remplacer/supprimer.)
4. Relancer `python3 build_db.py` : reconstruit entièrement `dataset_b.sqlite` (non versionné, voir
   `.gitignore`) à partir des CSV. **Les CSV sont la source de vérité, pas la base** — c'est ce qui rend
   la mise à jour simple : éditer un tableur, relancer le script, la base est toujours à jour.

## Pourquoi une base SQLite si les CSV suffisent déjà ?

Les CSV restent lisibles/éditables à la main (Excel, Google Sheets, éditeur de texte). La base SQLite
sert pour la suite : requêtes jointes (ex. corréler une mesure d'action avec les métriques calculées à
partir des photos par le pipeline de vision, §4 étape 6 — jalon go/no-go), sans devoir réécrire cette
logique de jointure à chaque fois.
