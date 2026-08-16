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

# Branches dont les FEUILLES portent des noms génériques d'instruments ("Guitare Acoustique",
# "Guitare Electrique", "Basse") : elles désignent en réalité des ÉTUIS pour ces instruments.
# Un nom nu appartenant à ces branches n'est jamais résolu — il est bien plus probable qu'il
# désigne l'instrument lui-même. Seul le chemin complet (que le prompt exige désormais) permet
# de classer un étui. Même raisonnement que l'exclusion de cette branche de la recherche floue
# côté frontend, en place depuis le 2026-08-01.
AMBIGUOUS_LEAF_BRANCHES = ('etui_housse',)


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


def canonicalize(classification, taxonomy, index=None):
    """Ramène une valeur de classification à un chemin canonique.

    Retourne `(chemin_ou_None, raison)` où `raison` vaut :
      - 'exact_path'  : déjà un chemin complet valide
      - 'leaf'        : nom de feuille unique, étendu en chemin complet
      - 'ambiguous'   : nom porté par plusieurs branches → NON résolu volontairement
      - 'unknown'     : absent de la taxonomie
      - 'empty'       : rien à résoudre
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
        if distinct[0].split('.')[0] in AMBIGUOUS_LEAF_BRANCHES:
            return None, 'ambiguous'
        return distinct[0], 'leaf'
    if len(distinct) > 1:
        return None, 'ambiguous'

    return None, 'unknown'
