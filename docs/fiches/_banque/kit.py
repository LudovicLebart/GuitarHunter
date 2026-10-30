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


def boite(x, y, largeur, hauteur, titre, sous_titre=None, couleur=None):
    """Case d'un organigramme (étape, décision, arrêt). `couleur` : trait et titre (défaut : bleu eau)."""
    col = couleur or C["eau_trait"]
    s = (f'<rect x="{x}" y="{y}" width="{largeur}" height="{hauteur}" rx="10" fill="#fff" stroke="{col}" stroke-width="3"/>'
         + texte(x + largeur / 2, y + 28, titre, 15, col, True, "middle"))
    if sous_titre:
        for i, ligne in enumerate(sous_titre.split("\n")):
            s += texte(x + largeur / 2, y + 50 + 18 * i, ligne, 13, C["texte_doux"], False, "middle")
    return s


def manche_profil(x, y, longueur=520, relief=0, frettes=14, corde=True, capo=False, etiquettes=False, pic=None):
    """Manche vu de côté, sillet à gauche. (x, y) = dessus de la touche au sillet.
    `relief` (px) = creux du milieu de la touche par rapport à la droite sillet-extrémité (0 = manche droit).
    14 frettes tracées à leurs vraies proportions ; la corde est la droite tendue au-dessus de la touche."""
    echelle = longueur / (1 - 2 ** (-frettes / 12))          # diapason en px
    xs = [x + echelle * (1 - 2 ** (-n / 12)) for n in range(1, frettes + 1)]
    fin = xs[-1]
    r = relief

    def surface(px):                                          # creux nul aux extrémités ; `pic` = position du creux maximal
        t = (px - x) / (fin - x)                              # (0 = sillet, 1 = dernière frette ; défaut : parabole, milieu)
        if pic is None:
            return y + 4 * r * t * (1 - t)
        t = min(max(t, 0.0), 1.0)
        maxi = pic ** (2 * pic) * (1 - pic) ** (2 * (1 - pic))
        return y + r * t ** (2 * pic) * (1 - t) ** (2 * (1 - pic)) / maxi

    haut = [f"{x + (fin - x) * k / 24:.1f},{surface(x + (fin - x) * k / 24):.1f}" for k in range(25)]
    bas = [f"{x + (fin - x) * k / 24:.1f},{surface(x + (fin - x) * k / 24) + 26:.1f}" for k in range(24, -1, -1)]
    s = [f'<polygon points="{" ".join(haut + bas)}" fill="{C["manche"]}" stroke="{C["bois_trait"]}" stroke-width="2"/>',
         f'<rect x="{x - 14}" y="{y - 12}" width="14" height="30" fill="#fff" stroke="{C["trait"]}" stroke-width="2"/>']
    for k, px in enumerate(xs, 1):
        s.append(f'<rect x="{px - 1.5:.1f}" y="{surface(px) - 3:.1f}" width="3" height="3" fill="{C["metal"]}"/>')
        if etiquettes and k in (1, 5, 8, 12):
            s.append(texte(f"{px:.1f}", f"{surface(px) + 46:.1f}", str(k), 12, C["texte_doux"], False, "middle"))
    if corde:
        s.append(f'<line x1="{x}" y1="{y - 6}" x2="{fin + 30:.1f}" y2="{y - 6}" stroke="#94a3b8" stroke-width="2"/>')
    if capo:
        s.append(f'<rect x="{xs[0] - 8:.1f}" y="{y - 24}" width="16" height="36" rx="3" fill="{C["noir"]}"/>')
    return "".join(s), xs


def frette_corde(x, y, hauteur=34, libelle=None):
    """Zoom sur une frette (coupe) avec la corde au-dessus ; flèche de mesure de la hauteur (action)."""
    s = (f'<rect x="{x - 70}" y="{y}" width="140" height="30" fill="{C["manche"]}"/>'
         f'<path d="M{x - 14} {y} q14 -12 28 0z" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="2"/>'
         f'<circle cx="{x}" cy="{y - 6 - hauteur - 5}" r="6" fill="#94a3b8" stroke="{C["trait"]}" stroke-width="2"/>'
         f'<path d="M{x + 44} {y - 9} V{y - 6 - hauteur - 5}" stroke="{C["alerte"]}" stroke-width="3"/>'
         f'<path d="M{x + 36} {y - 9} h16 M{x + 36} {y - 6 - hauteur - 5} h16" stroke="{C["alerte"]}" stroke-width="3"/>')
    if libelle:
        s += texte(x + 62, y - hauteur / 2 - 6, libelle, 14, C["alerte"], True)
    return s


def ecrou_rotation(x, y, sens="horaire"):
    """Écrou de truss rod vu de face avec flèche de rotation (horaire = serrer, antihoraire = desserrer)."""
    col = C["ok"] if sens == "horaire" else C["ko"]
    sweep = 1 if sens == "horaire" else 0
    p1, p2 = (x - 36, y - 6), (x + 36, y - 6)
    dx, dy = (0.6, 0.8) if sens == "horaire" else (0.6, -0.8)   # sens de la flèche au bout de l'arc
    return (f'<polygon points="{x - 18},{y - 31} {x + 18},{y - 31} {x + 36},{y} {x + 18},{y + 31} {x - 18},{y + 31} {x - 36},{y}" '
            f'fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="3"/>'
            f'<circle cx="{x}" cy="{y}" r="10" fill="{C["noir"]}"/>'
            f'<path d="M{p1[0]} {p1[1]} A 46 46 0 0 {sweep} {p2[0]} {p2[1]}" transform="translate(0 -22)" fill="none" stroke="{col}" stroke-width="5"/>'
            f'<polygon points="{p2[0] + 9 * dx:.1f},{p2[1] - 22 + 9 * dy:.1f} {p2[0] - 8 * dy:.1f},{p2[1] - 22 + 8 * dx:.1f} {p2[0] + 8 * dy:.1f},{p2[1] - 22 - 8 * dx:.1f}" fill="{col}"/>')
