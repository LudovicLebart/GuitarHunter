"""Règle d'arrêt « rattrapé » du scan Facebook (fonctions pures, testées dans test_catchup.py).

Les résultats sont triés par date de création décroissante : après une série d'annonces de la
zone toutes déjà connues et inchangées, on a rejoint le scan précédent, la suite est plus ancienne.
Seules les cartes de la zone comptent. Une carte hors zone ou sans lieu n'est jamais stockée,
donc elle ne dit rien sur l'avancement et ne remet rien à zéro.
"""


class CatchUpTracker:
    def __init__(self, known_run):
        # 0 (ou négatif) désactive la règle.
        self.known_run = known_run
        self.run = 0

    def known(self):
        """Une carte de la zone déjà connue et inchangée. True si on a rattrapé le scan précédent."""
        self.run += 1
        return self.done

    def unknown(self):
        """Une carte de la zone nouvelle ou modifiée : la série est rompue."""
        self.run = 0

    @property
    def done(self):
        return self.known_run > 0 and self.run >= self.known_run


def catchup_allowed(scans_done, full_pass_every):
    """Faut-il autoriser l'arrêt « rattrapé » pour le prochain scan d'une recherche donnée ?

    `scans_done` : scans complets déjà réussis pour cette recherche (ville, requête, budget, zone).
    Le premier scan est une passe complète : `should_skip_deal` rattache chaque annonce connue à
    l'utilisateur, ce que l'arrêt anticipé ferait manquer pour les cartes plus anciennes. Ensuite,
    une passe complète toutes les `full_pass_every` récupère une annonce indexée en retard par
    Facebook (apparue sous des annonces plus récentes déjà connues). `full_pass_every <= 0` : jamais
    de passe de contrôle.
    """
    if scans_done <= 0:
        return False
    return full_pass_every <= 0 or scans_done % full_pass_every != 0
