"""
Construit/reconstruit la base SQLite locale du Dataset B (docs/management/plans/NECK_RESET_VISION_PLAN.md
§4 étape 2, §5) à partir des 4 fichiers CSV de ce dossier (guitares/configurations/mesures/photos.csv).

Mise à jour "facile" : éditer les CSV dans Excel/Numbers/Google Sheets (ou un éditeur de texte) après
chaque séance de mesure — reprennent exactement les champs des 2 fiches imprimables
(docs/assets/dataset_b_protocole/) — puis relancer ce script. La base est entièrement reconstruite à
chaque exécution (DROP puis CREATE), donc toujours reproductible depuis les CSV : ce sont les CSV la
source de vérité, pas la base.

Les photos elles-mêmes restent des fichiers sur disque (pas stockées en binaire dans la base) : la
colonne chemin_fichier de photos.csv attend un chemin relatif à ce dossier (ex.
photos/<guitare_id>/<config_id>/1_ensemble.jpg), à charge de l'utilisateur d'y ranger les fichiers.

Usage :
  python3 backend/scripts/dataset_b/build_db.py
"""

import csv
import os
import sqlite3

HERE = os.path.dirname(__file__)
DB_PATH = os.path.join(HERE, "dataset_b.sqlite")

SCHEMA = """
CREATE TABLE guitares (
    guitare_id TEXT PRIMARY KEY,
    nom TEXT NOT NULL,
    type_jonction TEXT NOT NULL CHECK (type_jonction IN ('visse', 'collee')),
    longueur_diapason_mm REAL,
    notes TEXT
);

CREATE TABLE configurations (
    config_id TEXT PRIMARY KEY,
    guitare_id TEXT NOT NULL REFERENCES guitares(guitare_id),
    label TEXT NOT NULL,
    epaisseur_cale_mm REAL,
    position_cale TEXT CHECK (position_cale IN ('tete', 'corps', '') OR position_cale IS NULL),
    relief_mm REAL,
    date TEXT,
    mesureur TEXT,
    outil_mesure TEXT,
    notes TEXT
);

CREATE TABLE mesures (
    config_id TEXT PRIMARY KEY REFERENCES configurations(config_id),
    action_12e_mi_grave_mm REAL,
    action_12e_mi_aigu_mm REAL,
    diametre_corde_mi_grave_mm REAL,
    hauteur_sillet_chevalet_mm REAL,
    projection_chevalet_mm REAL,
    decollement_chevalet_table TEXT CHECK (decollement_chevalet_table IN ('oui', 'non', '') OR decollement_chevalet_table IS NULL),
    notes TEXT
);

CREATE TABLE photos (
    photo_id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_id TEXT NOT NULL REFERENCES configurations(config_id),
    type_vue TEXT NOT NULL CHECK (type_vue IN ('ensemble', 'sillet_chevalet', 'table_chevalet', '12e_frette', 'profil', 'type_annonce', 'ardoise', 'reglet_reference')),
    chemin_fichier TEXT NOT NULL,
    date_prise TEXT,
    notes TEXT
);
"""


def load_csv(name):
    path = os.path.join(HERE, name)
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def none_if_empty(v):
    return v if v not in (None, "") else None


def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    guitares = load_csv("guitares.csv")
    conn.executemany(
        "INSERT INTO guitares VALUES (?, ?, ?, ?, ?)",
        [(r["guitare_id"], r["nom"], r["type_jonction"], none_if_empty(r["longueur_diapason_mm"]), r["notes"]) for r in guitares],
    )

    configurations = load_csv("configurations.csv")
    conn.executemany(
        "INSERT INTO configurations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["config_id"], r["guitare_id"], r["label"], none_if_empty(r["epaisseur_cale_mm"]),
          none_if_empty(r["position_cale"]), none_if_empty(r["relief_mm"]), r["date"], r["mesureur"], r["outil_mesure"], r["notes"]) for r in configurations],
    )

    mesures = load_csv("mesures.csv")
    conn.executemany(
        "INSERT INTO mesures VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(r["config_id"], none_if_empty(r["action_12e_mi_grave_mm"]), none_if_empty(r["action_12e_mi_aigu_mm"]),
          none_if_empty(r["diametre_corde_mi_grave_mm"]), none_if_empty(r["hauteur_sillet_chevalet_mm"]),
          none_if_empty(r["projection_chevalet_mm"]), none_if_empty(r["decollement_chevalet_table"]), r["notes"]) for r in mesures],
    )

    photos = load_csv("photos.csv")
    conn.executemany(
        "INSERT INTO photos (config_id, type_vue, chemin_fichier, date_prise, notes) VALUES (?, ?, ?, ?, ?)",
        [(r["config_id"], r["type_vue"], r["chemin_fichier"], r["date_prise"], r["notes"]) for r in photos],
    )
    conn.commit()

    print(f"Base reconstruite -> {DB_PATH}")
    print(f"  guitares : {len(guitares)}")
    print(f"  configurations : {len(configurations)}")
    print(f"  mesures : {len(mesures)}")
    print(f"  photos : {len(photos)}")

    print("\n--- Aperçu (jointure configurations + mesures) ---")
    for row in conn.execute("""
        SELECT c.config_id, g.nom, c.label, m.action_12e_mi_grave_mm, m.hauteur_sillet_chevalet_mm
        FROM configurations c
        JOIN guitares g ON g.guitare_id = c.guitare_id
        LEFT JOIN mesures m ON m.config_id = c.config_id
        ORDER BY c.config_id
    """):
        print(f"  {row[0]:35s} | {row[1]:28s} | {row[2]:25s} | action_grave={row[3]} | sillet={row[4]}")

    conn.close()


if __name__ == "__main__":
    main()
