"""Banque d'éléments SVG pour illustrer les fiches techniques (`docs/fiches/`).

Chaque fonction renvoie un fragment SVG (chaîne) ; `svg()` les assemble en un fichier autonome. Les schémas
des fiches restent de simples fichiers `.svg` dans `docs/fiches/img/<slug>/` (le site n'exécute rien) : ce module
ne sert qu'à les FABRIQUER avec le même style. Voir `README.md` de ce dossier.

Usage :
    from kit import *
    corps = guitare_dessus(x=60, y=185, echelle=0.8)
    print(svg(820, 380, "Titre", "Description", corps + repere(1, 80, 300, "Guitare")))
"""
from xml.sax.saxutils import escape

# Palette commune (fond clair : les images s'affichent sur le thème sombre du site avec leur propre fond)
C = {
    "fond": "#f8fafc", "bois": "#f1dcb0", "bois_trait": "#7c4a1e", "manche": "#7c4a1e", "noir": "#1e293b",
    "texte": "#0f172a", "texte_doux": "#334155", "trait": "#475569", "eau": "#0ea5e9", "eau_fond": "#e0f2fe",
    "eau_trait": "#0284c7", "ruban": "#fde68a", "ruban_trait": "#a16207", "ok": "#15803d", "ko": "#b91c1c",
    "alerte": "#dc2626", "metal": "#cbd5e1", "colle": "#fbbf24", "vernis": "#b45309",
}
POLICE = "Arial, Helvetica, sans-serif"


def svg(largeur, hauteur, titre, description, corps):
    """Fichier SVG autonome : <title> et <desc> (accessibilité) + fond clair."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {largeur} {hauteur}" role="img" '
            f'aria-labelledby="t d" font-family="{POLICE}">\n'
            f'  <title id="t">{escape(titre)}</title>\n  <desc id="d">{escape(description)}</desc>\n'
            f'  <rect width="{largeur}" height="{hauteur}" fill="{C["fond"]}"/>\n{corps}\n</svg>\n')


def texte(x, y, t, taille=15, couleur=None, gras=False, ancre="start"):
    poids = ' font-weight="bold"' if gras else ""
    return (f'<text x="{x}" y="{y}" font-size="{taille}" fill="{couleur or C["texte"]}"{poids} '
            f'text-anchor="{ancre}">{escape(t)}</text>')


def repere(n, x, y, legende=None, couleur=None):
    """Pastille numérotée (1, 2, 3…) suivie d'une légende : le repère visuel des étapes."""
    s = (f'<circle cx="{x}" cy="{y}" r="15" fill="{couleur or C["texte"]}"/>'
         f'<text x="{x}" y="{y + 6}" font-size="17" font-weight="bold" fill="#fff" text-anchor="middle">{n}</text>')
    return s + (texte(x + 25, y + 6, legende) if legende else "")


def fleche(x1, y1, x2, y2, couleur=None, epaisseur=3):
    """Flèche droite simple (tête triangulaire)."""
    import math
    col = couleur or C["texte_doux"]
    a = math.atan2(y2 - y1, x2 - x1)
    p1 = (x2 - 14 * math.cos(a - 0.4), y2 - 14 * math.sin(a - 0.4))
    p2 = (x2 - 14 * math.cos(a + 0.4), y2 - 14 * math.sin(a + 0.4))
    return (f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{col}" stroke-width="{epaisseur}" fill="none"/>'
            f'<polygon points="{x2},{y2} {p1[0]:.1f},{p1[1]:.1f} {p2[0]:.1f},{p2[1]:.1f}" fill="{col}"/>')


# --- Guitare acoustique, vue de dessus (tête à droite). Repère local : queue en (0,0), axe en y = 0.
CORPS_DEMI = ("C0 -75 40 -150 105 -150 C160 -150 185 -112 205 -100 C225 -88 245 -118 280 -118 "
              "C320 -118 335 -85 345 -50")
CORPS_DEMI_RETOUR = ("C335 85 320 118 280 118 C245 118 225 88 205 100 C185 112 160 150 105 150 C40 150 0 75 0 0")


def guitare_dessus(x=0, y=0, echelle=1.0, manche=True, chevalet=True, rosace=True):
    """Guitare acoustique à plat : corps galbé (taille marquée), rosace, chevalet, manche, tête et mécaniques.
    (x, y) = queue du corps ; l'axe de la guitare est horizontal, la tête à droite."""
    g = [f'<g transform="translate({x} {y}) scale({echelle})">',
         f'<path d="M0 0 {CORPS_DEMI} L345 50 {CORPS_DEMI_RETOUR} Z" fill="{C["bois"]}" stroke="{C["bois_trait"]}" stroke-width="4"/>']
    if rosace:
        g.append(f'<circle cx="262" cy="0" r="38" fill="{C["noir"]}"/><circle cx="262" cy="0" r="42" fill="none" stroke="{C["bois_trait"]}" stroke-width="3"/>')
    if chevalet:
        g.append(f'<rect x="88" y="-42" width="18" height="84" rx="4" fill="{C["manche"]}"/>')
    if manche:
        g.append(f'<rect x="342" y="-19" width="300" height="38" fill="{C["manche"]}"/>'
                 f'<path d="M642 -19 L730 -34 L730 34 L642 19 Z" fill="{C["manche"]}"/>'
                 + "".join(f'<circle cx="{px}" cy="{py}" r="6" fill="{C["metal"]}"/>' for px in (672, 705) for py in (-18, 0, 18)))
    g.append("</g>")
    return "".join(g)


def coupe_table(x, y, largeur=330, epaisseur=34, vernis=True):
    """Coupe d'une portion de table (vue de côté). (x, y) = coin haut-gauche du bois."""
    s = (f'<polygon points="{x},{y} {x + largeur},{y} {x + largeur},{y + epaisseur} {x},{y + epaisseur}" '
         f'fill="{C["bois"]}" stroke="{C["trait"]}" stroke-width="2"/>')
    if vernis:
        s += f'<rect x="{x}" y="{y - 8}" width="{largeur}" height="8" fill="{C["vernis"]}" opacity=".55"/>'
    return s


def sac(x, y, largeur, hauteur, etiquette=None):
    """Sac plastique fermé : contour pointillé bleu."""
    s = (f'<rect x="{x}" y="{y}" width="{largeur}" height="{hauteur}" rx="26" fill="{C["eau_fond"]}" fill-opacity=".6" '
         f'stroke="{C["eau_trait"]}" stroke-width="3" stroke-dasharray="10 6"/>')
    if etiquette:
        s += texte(x + largeur / 2, y - 12, etiquette, 16, C["eau_trait"], True, "middle")
    return s


def bol_eponge(x, y, vapeur=True):
    """Bol d'eau avec éponge, vapeur facultative. (x, y) = coin haut-gauche du bol."""
    s = (f'<path d="M{x} {y} h120 l-14 46 h-92z" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="3"/>'
         f'<rect x="{x + 18}" y="{y - 22}" width="84" height="30" rx="9" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}" stroke-width="2"/>'
         f'<path d="M{x + 8} {y + 28} h104" stroke="{C["eau"]}" stroke-width="5"/>')
    if vapeur:
        s += f'<g fill="none" stroke="{C["eau"]}" stroke-width="2.5" stroke-linecap="round">' + "".join(
            f'<path d="M{x + dx} {y - 28} q-8 -10 0 -20 q8 -10 0 -20"/>' for dx in (38, 60, 82)) + "</g>"
    return s


def hygrometre(x, y, rayon=38):
    """Hygromètre rond : cadran, zone verte (plage normale), aiguille."""
    return (f'<circle cx="{x}" cy="{y}" r="{rayon}" fill="#fff" stroke="{C["trait"]}" stroke-width="3"/>'
            f'<path d="M{x - 28} {y + 18} a36 36 0 0 1 56 0" fill="none" stroke="{C["ok"]}" stroke-width="5" opacity=".8"/>'
            f'<path d="M{x} {y} l20 -22" stroke="{C["alerte"]}" stroke-width="4" stroke-linecap="round"/>'
            + texte(x, y + 33, "% HR", 11, C["texte_doux"], False, "middle"))


def ruban(x, y, largeur=55, hauteur=12):
    """Ruban de masquage (vu en coupe ou de dessus)."""
    return (f'<rect x="{x}" y="{y}" width="{largeur}" height="{hauteur}" fill="{C["ruban"]}" stroke="{C["ruban_trait"]}"/>')


def coton_tige(x, y):
    """Coton-tige tenant vers le bas ; la tête est en (x, y + 85)."""
    return (f'<rect x="{x - 8}" y="{y}" width="16" height="70" rx="3" fill="#e2e8f0" stroke="{C["trait"]}"/>'
            f'<ellipse cx="{x}" cy="{y + 85}" rx="11" ry="22" fill="#fff" stroke="{C["trait"]}"/>')


def bon_mauvais(x, y, bon=True):
    """Pastille ✓ (vert) ou ✗ (rouge) pour comparer un bon et un mauvais geste."""
    col, signe = (C["ok"], "✓") if bon else (C["ko"], "✗")
    return (f'<circle cx="{x}" cy="{y}" r="16" fill="{col}"/>'
            f'<text x="{x}" y="{y + 7}" font-size="21" font-weight="bold" fill="#fff" text-anchor="middle">{signe}</text>')
