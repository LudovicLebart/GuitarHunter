"""Critères d'arrêt du défilement des pages de résultats (Facebook, Kijiji) : fonctions pures."""


class ScrollProgress:
    """Suit le nombre de cartes chargées après chaque étape de défilement.

    `observe()` renvoie TARGET quand la cible est atteinte, STAGNANT quand le nombre n'a pas
    augmenté pendant `max_stagnant` étapes consécutives (fin de liste ou mur de connexion),
    sinon None.
    """
    TARGET = "target"
    STAGNANT = "stagnant"

    def __init__(self, target, max_stagnant=2):
        self.target = target
        self.max_stagnant = max_stagnant
        self.previous = 0
        self.stagnant = 0

    def observe(self, count, scrolled=True):
        """`scrolled=False` : lecture initiale, avant tout défilement (ne compte pas comme stagnation)."""
        if count >= self.target:
            return self.TARGET
        if scrolled and count <= self.previous:
            self.stagnant += 1
            if self.stagnant >= self.max_stagnant:
                return self.STAGNANT
        else:
            self.stagnant = 0
        self.previous = count
        return None
