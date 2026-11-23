"""Garde-fou de `constraints.txt` (R-9-6, 2026-11-10) : le fichier fige les versions installées par `deploy.yml`
(`pip install -r requirements.txt -c constraints.txt`). Chaque dépendance de `requirements.txt` doit y avoir une version
exacte ; sinon elle redevient « dernière version » à chaque déploiement sans que rien ne le signale.
Procédure de rafraîchissement : docs/reference/exploitation.md, section « Versions figées ». Sans réseau."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _name(requirement):
    """`uvicorn[standard]` -> `uvicorn`, `psycopg[binary,pool]>=3` -> `psycopg`, normalisé (casse, `_`/`-`/`.`)."""
    base = re.split(r"[\[<>=!~; ]", requirement.strip(), maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", base).lower()


def _lines(filename):
    with open(os.path.join(ROOT, filename), encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]


class TestConstraints(unittest.TestCase):
    def test_every_requirement_is_pinned_exactly(self):
        pinned = {}
        for line in _lines("constraints.txt"):
            match = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([^\s;]+)", line)
            self.assertIsNotNone(match, f"ligne de constraints.txt qui n'est pas `paquet==version` : {line!r}")
            pinned[_name(match.group(1))] = match.group(2)
        missing = sorted(_name(r) for r in _lines("requirements.txt") if _name(r) not in pinned)
        self.assertEqual(missing, [], f"dépendances de requirements.txt absentes de constraints.txt : {missing}")

    def test_file_has_unix_line_endings(self):
        with open(os.path.join(ROOT, "constraints.txt"), "rb") as fh:
            self.assertNotIn(b"\r", fh.read(), "constraints.txt doit rester en LF (.gitattributes)")


if __name__ == "__main__":
    unittest.main()
