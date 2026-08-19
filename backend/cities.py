"""Clé canonique et libellé d'affichage d'une ville (2026-08-16).

Problème constaté dans les statistiques : la même ville apparaît sous plusieurs graphies —
`Montréal, QC`, `montreal`, `St-Jean-sur-Richelieu,QC` — et se retrouve donc comptée plusieurs
fois dans les regroupements par ville.

Ce ne sont pas des fautes de frappe mais **deux producteurs qui écrivent deux formats** :
  - Facebook stocke la chaîne scrapée telle quelle (`"Montréal, QC"`, virgule parfois collée) ;
  - Kijiji écrivait `nearest_configured_city()['city']`, c'est-à-dire la **clé normalisée** de la
    ville (minuscules, sans accents) — d'où `montreal` à côté de `Montréal, QC`.

Deux notions distinctes, à ne jamais confondre :
  - la **clé canonique** (`normalize_city_key`) sert à REGROUPER — insensible aux accents, à la
    casse, aux tirets, aux abréviations Saint/St et à la région ;
  - le **libellé** sert à AFFICHER — on conserve la plus riche des graphies rencontrées
    (accents + région), conformément au choix produit « Ville, RÉGION » (ex: `Montréal, QC`).

⚠️ La clé IGNORE la région, volontairement : c'est ce qui permet de réunir `montreal` (Kijiji,
sans région) et `Montréal, QC` (Facebook). Conséquence à connaître : deux villes homonymes de
régions différentes (`Paris, IDF` et `Paris, ON`) partagent la même clé. `regions_conflict()`
sert à ne PAS les fusionner lors d'une réécriture destructive — un regroupement d'affichage est
réversible, une réécriture en base ne l'est pas.
"""

import unicodedata

# Abréviations courantes des toponymes québécois, à développer avant comparaison.
CITY_ABBREVIATIONS = {'st': 'saint', 'ste': 'sainte'}


def normalize_city_key(raw):
    """Clé de regroupement d'une ville.

    Implémentation de référence, volontairement SANS dépendance : `ListingParser` (qui portait
    historiquement cette logique) importe Playwright, ce qui rendait impossible de normaliser
    un nom de ville depuis un script léger ou un test. `ListingParser.normalize_city_name`
    délègue désormais ici — une seule implémentation, donc aucun risque que les deux dérivent
    et se mettent à regrouper différemment.
    """
    if not raw:
        return ""
    # 1. Partie avant la virgule (la région ne discrimine pas la ville) et minuscules
    name = str(raw).split(',')[0].strip().lower()
    # 2. Tirets et points -> espaces, pour uniformiser "St-Jean" et "St Jean"
    name = name.replace('-', ' ').replace('.', ' ')
    # 3. Abréviations Saint/Sainte
    name = " ".join(CITY_ABBREVIATIONS.get(w, w) for w in name.split())
    # 4. Accents retirés
    return unicodedata.normalize('NFD', name).encode('ascii', 'ignore').decode('utf-8')


def score_label(raw):
    """Note la « richesse » d'une graphie, pour choisir laquelle afficher.

    Priorité, dans l'ordre : présence d'une région après la virgule (`Montréal, QC` bat
    `Montréal`), présence d'accents ou de majuscules (`Montréal` bat `montreal`), puis longueur.
    Déterministe : à score égal, l'ordre alphabétique tranche, pour que deux exécutions du même
    audit produisent exactement le même résultat.
    """
    if not raw:
        return (0, 0, 0)
    text = str(raw)
    has_region = 1 if (',' in text and text.split(',', 1)[1].strip()) else 0
    has_diacritics_or_case = 1 if any(c.isupper() for c in text) or any(
        ord(c) > 127 for c in text
    ) else 0
    return (has_region, has_diacritics_or_case, len(text))


def pick_best_label(labels):
    """Choisit la graphie à afficher parmi toutes celles observées pour une même ville."""
    candidates = [l for l in labels if l and str(l).strip()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda l: (score_label(l), str(l)), reverse=True)[0]


def extract_region(raw):
    """Région d'une graphie (`"Montréal, QC"` -> `"qc"`), ou `""` si absente."""
    if not raw or ',' not in str(raw):
        return ""
    return str(raw).split(',', 1)[1].strip().lower()


def regions_conflict(labels):
    """`True` si deux graphies portent des régions explicites DIFFÉRENTES.

    Sert de garde-fou avant toute réécriture : `Paris, IDF` et `Paris, ON` ont la même clé mais
    ne sont pas la même ville. Une graphie sans région (`Paris`) n'entre pas en conflit — elle
    est simplement moins précise.
    """
    regions = {extract_region(l) for l in labels or []}
    regions.discard("")
    return len(regions) > 1


def format_city_label(name, reference=None):
    """Libellé d'affichage pour une ville configurée.

    `name` est le nom saisi par l'utilisateur dans son catalogue de villes (accentué, ex:
    `Montréal`). `reference` est une graphie déjà observée pour cette même ville (typiquement
    côté Facebook, ex: `Montréal, QC`) : si elle porte une région, on la reprend telle quelle
    pour que les deux sources produisent exactement la même chaîne.
    """
    if not name:
        return reference or None
    if reference and normalize_city_key(reference) == normalize_city_key(name):
        return pick_best_label([name, reference])
    return str(name).strip()
