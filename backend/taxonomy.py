"""Canonicalisation de la classification renvoyée par l'IA (2026-08-16).

Contexte : `analyzer.py` fait un `json.loads()` brut, sans `response_schema` ni énumération — rien
ne garantit que la valeur de `classification` appartienne réellement à la taxonomie. En pratique
l'IA renvoyait indifféremment un nom de feuille ("Parlor Standard"), un chemin complet
("guitare.electrique.lespaul") ou une valeur inventée, le prompt ne précisant pas le format attendu.

Le nom de feuille seul est **structurellement ambigu** : `Guitare Electrique` est à la fois une
feuille de `etui_housse.Etui_Rigide` (un étui) et le libellé de la branche `guitare.electrique`
(l'instrument). C'est ce qui faisait apparaître des étuis comme des guitares électriques.

Ce module ramène toute valeur à un **chemin complet en dot-notation**, seul format non ambigu, et
refuse explicitement de trancher quand le nom est porté par plusieurs branches — mieux vaut une
annonce non classée (corrigeable à la main depuis l'app) qu'une annonce rangée dans la mauvaise
catégorie sans que personne ne s'en aperçoive.
"""

import unicodedata
import re

# Branche des contenants, dont CERTAINES feuilles portent des noms génériques d'instruments
# ("Guitare Acoustique", "Guitare Electrique") alors qu'elles désignent des étuis pour ces
# instruments. Un tel nom nu n'est jamais résolu : il est bien plus probable qu'il désigne
# l'instrument lui-même.
#
# ⚠️ Restreint le 2026-08-16 après l'audit en production : la règle bloquait AUPARAVANT toute
# feuille de cette branche, y compris `Housse_Souple`, `Gigbag Standard`, `ATA Road Case` ou
# `Etui_Rigide` — des termes d'étui purs, sans la moindre ambiguïté, que rien ne justifiait de
# refuser (≈19 annonces correctement classées rendues invisibles). Seuls sont désormais bloqués
# les noms qui COMMENCENT par un nom de famille d'instrument, déduit dynamiquement des racines
# de la taxonomie plutôt que codé en dur.
CONTAINER_BRANCHES = ('etui_housse',)

# Nombre minimum de segments d'un chemin partiel accepté pour une réparation par suffixe :
# en dessous, on retombe sur une résolution par nom nu, avec le risque d'ambiguïté que ça implique.
MIN_PARTIAL_PATH_SEGMENTS = 2


def normalize_segment(text):
    """Minuscules, sans accents, alphanumérique uniquement — pour UN segment de chemin."""
    if not text:
        return ''
    decomposed = unicodedata.normalize('NFD', str(text))
    without_accents = ''.join(c for c in decomposed if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]', '', without_accents.lower())


def normalize_path(text):
    """Normalise un chemin en CONSERVANT le séparateur '.'.

    Le point porte du sens : sans lui, "Guitare Electrique" et "guitare.electrique" produisent la
    même clé (le bug des étuis). Miroir exact de `src/utils/taxonomy.js::normalizePath` côté front.
    """
    segments = [normalize_segment(s) for s in str(text or '').split('.')]
    return '.'.join(s for s in segments if s)


def build_index(taxonomy):
    """Construit `(by_path, by_leaf)` à partir de l'arbre `taxonomy_master`.

    `by_leaf` associe un nom normalisé à la LISTE des nœuds qui le portent (pas à un seul) : c'est
    ce qui permet de détecter l'ambiguïté au lieu de l'écraser silencieusement.

    Un nom "porté" recouvre DEUX façons de désigner le même texte, et c'est le cœur du bug des
    étuis : `Guitare Electrique` est une feuille de `etui_housse.Etui_Rigide`, mais c'est aussi la
    lecture naturelle du CHEMIN `guitare.electrique` une fois ses points retirés. Les deux sont
    donc enregistrés sous la même clé, ce qui rend le nom nu détectable comme ambigu — quel que
    soit le sens dans lequel l'IA l'a employé. Sans ça on ne fait que déplacer l'erreur : avant le
    correctif un étui devenait une guitare, avec un index par feuille seule une guitare deviendrait
    un étui.
    """
    by_path = {}
    by_leaf = {}

    def register(segments):
        by_path[normalize_path('.'.join(segments))] = list(segments)
        for key in {normalize_segment(segments[-1]), normalize_path('.'.join(segments)).replace('.', '')}:
            if key:
                by_leaf.setdefault(key, []).append(list(segments))

    def traverse(node, current):
        if isinstance(node, list):
            for item in node:
                register(current + [item])
        elif isinstance(node, dict):
            for key, value in node.items():
                segments = current + [key]
                register(segments)
                traverse(value, segments)

    traverse(taxonomy or {}, [])
    return by_path, by_leaf


def _instrument_roots(by_path):
    """Racines de la taxonomie désignant des objets (guitare, amplificateur…), hors contenants."""
    roots = {segments[0] for segments in by_path.values()}
    return {normalize_segment(r) for r in roots if r not in CONTAINER_BRANCHES}


def _repair_partial_path(classification, by_path):
    """Étend un chemin INCOMPLET vers l'unique chemin canonique qui s'y termine.

    L'audit en production a montré que l'IA produit régulièrement des chemins presque bons :
    racine oubliée (`electrique.solid_body.Double_Cut.SG`), niveau intermédiaire sauté
    (`guitare.acoustique_acier.Travel.Baby / Mini`, sans `specialites`) ou racine renommée depuis
    (`accessoire_etui.protection.Etui_Rigide.…`). Tous désignent sans ambiguïté une seule
    catégorie — les jeter revenait à perdre de l'information déjà correcte.

    On cherche donc les chemins canoniques qui SE TERMINENT par les segments fournis, en retirant
    au besoin les premiers segments de l'entrée (racine inventée). Un résultat n'est accepté que
    s'il est UNIQUE et qu'il reste au moins `MIN_PARTIAL_PATH_SEGMENTS` segments à comparer.
    """
    segments = [s for s in normalize_path(classification).split('.') if s]
    canonical_paths = list(by_path.values())

    while len(segments) >= MIN_PARTIAL_PATH_SEGMENTS:
        suffix = '.' + '.'.join(segments)
        matches = {
            '.'.join(path) for path in canonical_paths
            if normalize_path('.'.join(path)).endswith(suffix)
        }
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            return None  # Plusieurs cibles possibles : on ne devine pas.
        segments = segments[1:]  # Racine inventée/obsolète : on la retire et on réessaie.

    return None


def canonicalize(classification, taxonomy, index=None):
    """Ramène une valeur de classification à un chemin canonique.

    Retourne `(chemin_ou_None, raison)` où `raison` vaut :
      - 'exact_path'   : déjà un chemin complet valide
      - 'leaf'         : nom de feuille unique, étendu en chemin complet
      - 'partial_path' : chemin incomplet étendu vers l'unique chemin canonique correspondant
      - 'ambiguous'    : nom porté par plusieurs branches → NON résolu volontairement
      - 'unknown'      : absent de la taxonomie
      - 'empty'        : rien à résoudre
    """
    if not classification:
        return None, 'empty'

    by_path, by_leaf = index if index else build_index(taxonomy)

    path_key = normalize_path(classification)
    if path_key in by_path:
        return '.'.join(by_path[path_key]), 'exact_path'

    # Nom nu : on dédoublonne les chemins candidats (un même nœud peut être enregistré sous
    # plusieurs clés). Plus d'un nœud distinct = ambigu, on refuse de trancher.
    candidates = by_leaf.get(normalize_segment(classification)) or []
    distinct = sorted({'.'.join(c) for c in candidates})
    if len(distinct) == 1:
        segments = distinct[0].split('.')
        # Feuille d'un contenant : refusée seulement si son nom commence par un nom de famille
        # d'instrument ("Guitare Acoustique" → probablement l'instrument, pas l'étui). Les termes
        # d'étui purs ("Housse_Souple", "ATA Road Case") passent normalement.
        if segments[0] in CONTAINER_BRANCHES:
            leaf_key = normalize_segment(segments[-1])
            if any(leaf_key.startswith(root) for root in _instrument_roots(by_path)):
                return None, 'ambiguous'
        return distinct[0], 'leaf'
    if len(distinct) > 1:
        return None, 'ambiguous'

    # Chemin incomplet (racine oubliée, niveau sauté, racine obsolète) : extensible sans ambiguïté.
    repaired = _repair_partial_path(classification, by_path)
    if repaired:
        return repaired, 'partial_path'

    return None, 'unknown'
