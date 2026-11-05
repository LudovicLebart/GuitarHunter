"""Coupe latérale d'une acoustique au joint manche / corps : LA géométrie commune des schémas de la série « neck reset ».

Même vue partout : manche à gauche, corps à droite, table à plat. On voit la touche (bande sombre, frettes), la rallonge de
touche posée sur la table au-dessus de la rosace, le talon contre le corps, la queue d'aronde dans le tasseau, le vide au
fond de la mortaise, la table, le fond, le chevalet et son sillet. Un schéma ne redessine jamais cela : il crée une `Coupe`,
choisit l'angle du manche, et ajoute ses propres annotations (cotes, flèches, outils).

    from coupe import Coupe
    c = Coupe(angle=0)                                  # avant la remise en angle
    morceaux = [c.corps(), c.manche(), c.chevalet()]
    c.P, c.selle, c.pt(u, v)                            # points d'ancrage pour les annotations

Repère du manche : origine en P (la touche rejoint la table au joint), u vers la droite (vers le corps), v vers le bas.
`angle` (degrés) : rotation du manche autour de P, positive = tête vers le bas, donc la règle posée sur les frettes monte
vers le chevalet. Tout est exagéré, rien n'est à l'échelle.
"""
import math

from kit import C, texte

TOUCHE = 10         # épaisseur de la touche
MANCHE = 34         # épaisseur du manche sous la touche
TALON_L = 62        # largeur du talon
TALON_H = 120       # hauteur du talon le long du corps (la mesure B)
RALLONGE = 170      # longueur de la rallonge de touche au-delà du joint
TABLE = 12          # épaisseur de la table
FOND = 140          # profondeur du corps sous la table
TASSEAU = 46        # largeur du tasseau
OUIE = (120, 250)   # début et fin de la rosace, comptés depuis le joint
SELLE = 310         # distance du joint au sillet de chevalet (la mesure C)
FRETTES = (-278, -240, -202, -164, -125, -85, -44, -2, 40, 80, 118, 154)   # positions (u) des frettes ; la 14e est en -2, la 15e en 40
FRETTE_15 = 40      # la 15e frette : sa fente donne sur le fond de la queue d'aronde
TENON = ((0, 0), (36, 0), (36, 50), (0, 50))     # queue d'aronde vue de côté : un bloc sous la touche (l'évasement se voit de dessus)
VIDE = (36, 46, 0, 50)                           # vide au fond de la mortaise (u0, u1, v0, v1), sous la touche
BRIDE = 36          # hauteur du chevalet


class Coupe:
    def __init__(self, jx=330, yt=200, angle=0.0, longueur=290, corps=400, ouie=None):
        """`ouie` : (début, fin) de la rosace comptés depuis le joint ; par défaut `OUIE`. Les schémas centrés sur la rallonge
        la reculent (début > RALLONGE) pour que le bout de la rallonge repose sur la table."""
        self.jx, self.yt, self.angle, self.longueur, self.largeur_corps = jx, yt, angle, longueur, corps
        self.ouie = ouie or OUIE
        self.P = (jx, yt)
        self.selle = (jx + SELLE, yt - BRIDE)            # haut du chevalet, à l'aplomb du milieu du sillet
        self.fond_y = yt + FOND

    # -- géométrie ------------------------------------------------------------------------------------------------------
    def pt(self, u, v, angle=None):
        """Point du manche (u, v) amené dans le dessin, pour l'angle donné (défaut : celui de la coupe)."""
        a = math.radians(self.angle if angle is None else angle)
        return (self.jx + u * math.cos(a) + v * math.sin(a), self.yt - u * math.sin(a) + v * math.cos(a))

    @staticmethod
    def poly(points, fill, stroke, ep=2, extra=""):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        return f'<polygon points="{pts}" fill="{fill}" stroke="{stroke}" stroke-width="{ep}"{extra}/>'

    # -- corps ----------------------------------------------------------------------------------------------------------
    def corps(self, vide=True, legende_ouie=True):
        """Tasseau (sa mortaise reçoit la queue d'aronde, sous la touche), table interrompue par la rosace, fond, éclisse.
        `vide` : le vide au fond de la queue d'aronde."""
        x, y = self.jx, self.yt
        o0, o1 = x + self.ouie[0], x + self.ouie[1]
        fin = x + self.largeur_corps
        bois, tr = C["bois"], C["bois_trait"]
        s = [
            f'<rect x="{x}" y="{y}" width="{TASSEAU}" height="{FOND}" fill="#e8cf9b" stroke="{tr}" stroke-width="2"/>',
            f'<rect x="{x + TASSEAU}" y="{y}" width="{o0 - x - TASSEAU}" height="{TABLE}" fill="{bois}" stroke="{tr}" stroke-width="2"/>',
            f'<rect x="{o1}" y="{y}" width="{max(fin - o1, 0)}" height="{TABLE}" fill="{bois}" stroke="{tr}" stroke-width="2"/>'
            if fin > o1 else "",
            f'<rect x="{x}" y="{y + FOND}" width="{fin - x}" height="10" fill="{bois}" stroke="{tr}" stroke-width="2"/>',
            f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + FOND + 10}" stroke="{tr}" stroke-width="4"/>',
        ]
        if legende_ouie and fin > o1:
            s.append(texte((o0 + o1) / 2, y + 34, "rosace", 13, C["texte_doux"], False, "middle"))
        if vide:
            u0, u1, v0, v1 = VIDE
            s.append(f'<rect x="{x + u0}" y="{y + v0}" width="{u1 - u0}" height="{v1 - v0}" fill="{C["eau_fond"]}" '
                     f'stroke="{C["eau_trait"]}" stroke-width="1.5"/>')
        return "".join(s)

    def chevalet(self):
        """Chevalet, avec son sillet qui dépasse un peu. Le haut du chevalet est `self.selle`."""
        sx, sy = self.selle
        return (f'<rect x="{sx - 32}" y="{sy}" width="64" height="{BRIDE}" fill="{C["noir"]}" stroke="{C["trait"]}" stroke-width="2"/>'
                f'<rect x="{sx - 3}" y="{sy - 6}" width="6" height="8" fill="{C["metal"]}" stroke="{C["trait"]}" stroke-width="1.5"/>')

    # -- manche ---------------------------------------------------------------------------------------------------------
    def manche(self, angle=None, fantome=False, frettes=True, rallonge=True, sans_15=False):
        """Manche, talon (face verticale contre le corps), queue d'aronde, touche, frettes, rallonge. `fantome` : contour pointillé ;
        `sans_15` : la 15e frette est retirée (étape 2 de la fiche)."""
        a = self.angle if angle is None else angle
        t = math.tan(math.radians(a))
        pt = lambda u, v: self.pt(u, v, a)   # noqa: E731
        corps = [pt(-self.longueur, 0), pt(0, 0), pt(-TALON_H * t, TALON_H), pt(-TALON_L, TALON_H),
                 pt(-TALON_L, MANCHE), pt(-self.longueur, MANCHE)]
        fin = RALLONGE if rallonge else 0
        touche = [pt(-self.longueur, -TOUCHE), pt(fin, -TOUCHE), pt(fin, 0), pt(-self.longueur, 0)]
        if fantome:
            return (self.poly(corps, "none", C["trait"], 2, ' stroke-dasharray="6 4"')
                    + self.poly(touche, "none", C["trait"], 2, ' stroke-dasharray="6 4"'))
        s = [self.poly(self.tenon(), C["manche"], C["bois_trait"], 2),
             self.poly(corps, C["manche"], C["bois_trait"], 2),
             self.poly(touche, C["noir"], C["trait"], 2)]
        if frettes:
            for u in FRETTES:
                if -self.longueur < u < fin and not (sans_15 and u == FRETTE_15):
                    (x1, y1), (x2, y2) = pt(u, -TOUCHE - 3), pt(u, -TOUCHE)
                    s.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{C["metal"]}" stroke-width="3"/>')
        return "".join(s)

    def tenon(self):
        """Contour de la queue d'aronde, dans la mortaise : elle reste dans le corps, elle ne tourne pas avec le manche."""
        return [self.pt(u, v, 0) for u, v in TENON]

    def cale_sur_touche(self, u0, u1, couleur=None):
        """Cale posée sur la touche (entre u0 et u1), parallèle à elle ; elle ne touche que la touche, pas les frettes."""
        pts = [self.pt(u0, -TOUCHE - 3), self.pt(u1, -TOUCHE - 3), self.pt(u1, -TOUCHE - 18), self.pt(u0, -TOUCHE - 18)]
        return self.poly(pts, couleur or C["bois"], C["bois_trait"], 2)

    def fente_15(self):
        """La fente de la 15e frette : une entaille claire dans la touche (le vide se trouve dessous)."""
        (x1, y1), (x2, y2) = self.pt(FRETTE_15, -TOUCHE), self.pt(FRETTE_15, 0)
        return f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{C["fond"]}" stroke-width="4"/>'

    def coin_talon(self, gamma_avant, gamma_apres, angle=None):
        """Le coin à retirer en bas du talon, entre la face d'avant et la face d'après (angles en degrés), tel qu'il est dans le manche."""
        pt = lambda u, v: self.pt(u, v, angle)   # noqa: E731
        ta, tb = math.tan(math.radians(gamma_avant)), math.tan(math.radians(gamma_apres))
        return self.poly([pt(0, 0), pt(-TALON_H * ta, TALON_H), pt(-TALON_H * tb, TALON_H)], C["ko"], C["ko"], 2, ' fill-opacity=".6"')
