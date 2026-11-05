# Constats de revue — section 3 : scraping

Relevés le 2026-11-05 pendant la passe « deepdocument » (commit `f1075b3`). Rien n'a été corrigé. Format : voir [README](README.md). « Confirmé » = reproduit ou mesuré ; sinon à confirmer sur un vrai site (aucun test n'exerce Facebook ou Kijiji).

### R-3-1 — `parse_details_page` : `time.sleep` plante en silence à cause d'un `import time` local
- Où : `backend/scraping/parser.py:172` (appel) et `:240` (`import time` dans `if not published_at_ts:`).
- Catégorie : bug · Gravité : moyenne à haute (effet réel à mesurer)
- Constat (confirmé sur le motif, reproduit isolément) : un `import time` dans le corps d'une fonction rend `time` local à toute la fonction. Au premier appel de `time.sleep(0.8)` (ligne 172), Python lève `UnboundLocalError`, avalée par le `except: pass` voisin. La pause entre deux photos du carrousel n'a donc jamais lieu : la flèche droite est pressée, puis la lecture suivante se fait sans attendre le chargement. Les photos peuvent être moins nombreuses que sur la fiche réelle, ce qui dégrade l'analyse IA et pourrait contribuer aux cas « 0 image » diagnostiqués. Le `except:` nu masque aussi toute autre erreur de ce bloc.
- Piste : supprimer l'`import time` local (le module est déjà importé en tête) ; remplacer les `except:` nus par `except Exception`.
- À confirmer : comparer le nombre de photos extraites avant et après correction sur quelques annonces.

### R-3-2 — La vérification de disponibilité marque « vendue » une annonce lors d'un blocage anti-bot
- Où : `backend/scraping/core.py:773` (`"/marketplace/item/" not in page.url`), `backend/scraping/kijiji/core.py:698` (`"/v-" not in page.url`).
- Catégorie : bug · Gravité : haute (à confirmer en situation de blocage)
- Constat : sur une redirection vers `/login` ou une page captcha, l'URL ne contient plus le chemin de l'annonce, la fonction renvoie « indisponible » et `bot._check_listings_availability` appelle `mark_deal_as_sold` (vente **globale**). Les scans de recherche testent bien `/login` et `captcha`, pas cette fonction. Un blocage pendant un nettoyage (toutes les 6 h, toutes les annonces) pourrait marquer des centaines d'annonces comme vendues.
- Piste : traiter login, captcha et checkpoint comme « indéterminé » (annonce considérée disponible), et interrompre le nettoyage après quelques blocages.

### R-3-3 — Faux positifs « vendue » sur des phrases de description
- Où : `core.py:795-804` (Facebook : `span`, `div[role=button]`, `h1`, `h2`), `kijiji/core.py:711-746` (Kijiji : tous les `div`).
- Catégorie : bug probable · Gravité : moyenne
- Constat : les motifs `plus disponible`, `no longer available`, `out of stock` ne sont pas ancrés. Une description contenant « cet accessoire n'est plus disponible séparément » (dans un `span`, ou dans le texte du conteneur côté Kijiji, dont `innerText` agrège toute la page) déclenche la vente. Le commentaire du code parle de frontières de mots mais seuls les motifs « vendu » et « sold » sont ancrés.
- Piste : ancrer tous les motifs, ou limiter la recherche au bloc de statut de l'annonce.

### R-3-4 — La géolocalisation par ville n'est jamais appliquée (code mort)
- Où : `backend/scraping/core.py:415-422` (`self.city_coordinates.get(...)`), `backend/bot.py:817` (`FacebookScraper({}, {}, …)`).
- Catégorie : code-mort / doc-code · Gravité : basse à moyenne
- Constat : le scraper ne reçoit jamais de `city_coordinates` (le bot passe `{}`), donc `set_geolocation` n'est jamais appelé. Toutes les sessions Facebook portent la géolocalisation par défaut de `ScraperConfig` (Montréal), même pour une ville comme Québec ou Gatineau. Le commentaire du code dit que ce réglage évite les annonces « Ship to you » dues à l'IP. À confirmer : si l'ID de ville dans l'URL suffit, le code est simplement inutile ; sinon c'est un défaut.
- Piste : soit alimenter `city_coordinates` depuis le bot, soit supprimer le bloc.

### R-3-5 — Villes d'ancrage Kijiji homonymes d'autres provinces
- Où : `backend/scraping/kijiji/locations.py:44` (`_HUB_CANDIDATE_EXCLUSIONS = {"richmond"}`), `build_resolvable_hubs`.
- Catégorie : bug probable · Gravité : moyenne
- Constat (mesuré, 23 ancrages résolvables) : la liste contient notamment `bedford`, `hope`, `saint-albert`, dont le nom se résout chez Kijiji vers une ville d'une autre province. Une ville sans sous-zone propre, proche de la municipalité québécoise du même nom, serait ancrée sur le lieu Kijiji de l'homonyme. L'ancrage devrait être « raisonnablement proche » selon la docstring.
- Piste : valider chaque ancrage par la distance entre la municipalité et les coordonnées du lieu Kijiji, ou exclure à la main (pas de liste exhaustive aujourd'hui, un seul nom exclu).

### R-3-6 — La date de publication retombe silencieusement sur la date de scraping
- Où : `backend/scraping/parser.py:239-242`, `parse_french_date` (formules françaises uniquement).
- Catégorie : bug / qualité des statistiques · Gravité : moyenne
- Constat : si le libellé n'est pas reconnu (page en anglais, autre formulation, libellé absent), `published_at_ts` reçoit l'heure du scan. Le tri « date de publication » et les statistiques de délai de vente (voir `donnees.md`) seront faux sans avertissement autre qu'un message d'information. Le décalage de « il y a N mois » est calculé à 30 jours.
- Piste : laisser `published_at_ts` nul quand la date est inconnue, et le traiter côté interface.

### R-3-7 — Image de remplacement enregistrée comme photo de l'annonce
- Où : `backend/scraping/parser.py:93` et `kijiji/parser.py:65` (`https://via.placeholder.com/400`), `bot.py:464` (garde « aucune photo et prix 0 »).
- Catégorie : bug probable · Gravité : basse
- Constat : une carte sans image reçoit une URL de service externe comme `imageUrl`. Elle compte comme « image présente » dans la garde de `handle_deal_found`, et peut être téléchargée puis envoyée vers Firebase Storage comme photo. Le domaine `via.placeholder.com` est un service tiers qui n'est plus garanti.
- Piste : `None` plutôt qu'une URL.

### R-3-8 — Boucle de lecture séquentielle et attentes fixes
- Où : `core.py:602-618` (une fiche détail à la fois, `time.sleep(2)` + attentes), `kijiji/core.py:538-566`, `core.py:945` et `bot.py` (pause de 2 s entre ancrages).
- Catégorie : performance · Gravité : basse
- Constat : chaque annonce retenue coûte une navigation complète (60 s de délai maximal) puis 2 s de pause, sans parallélisme ; le navigateur reste ouvert pendant ce temps (voir R-2-3). Les pauses fixes sont aussi un motif de comportement régulier, ce que le reste du code cherche à éviter.
- Piste : pauses aléatoires ; pas de changement de structure sans mesure.

### R-3-9 — Code et modules sans appelant
- Où : `FacebookScraper.get_city_id_and_coords` (`core.py:126-195`, seulement des scripts), `KijijiScraper.scan_marketplace` (champ de recherche d'accueil, filtre de lieu inopérant), `backend/scraping_leboncoin/` (scripts de sondage seulement), `_REGION_ALIASES` de compatibilité dans `city_finder.py`, `import sys`/`sys.path.append` et `try/except ImportError` autour de `from config import PROXIES` (`core.py:9-18`).
- Catégorie : code-mort / simplification · Gravité : basse
- Piste : supprimer ou isoler dans `scripts/` ; remplacer le `sys.path.append` par l'import normal.

### R-3-10 — `config.py` écrit dans la sortie standard à l'import
- Où : `config.py` (messages « [OK] Multi-utilisateurs (Seed) : … » et « [OK] Prompts par défaut… » constatés à chaque import, uid compris).
- Catégorie : hygiène · Gravité : basse
- Constat : tout script ou test qui importe `config` affiche l'identifiant d'un utilisateur ; l'import déclenche aussi la lecture du fichier de prompts.
- Piste : journaliser en `debug`, sans uid.

### R-3-11 — Garde-fous incomplets du suivi `last_scan` de Kijiji
- Où : `kijiji/core.py:88` (attribut de classe mutable) et `:415`, `:492`.
- Catégorie : robustesse · Gravité : basse
- Constat : `last_scan` est un dictionnaire de classe ; seul `scan_search_url` le réinitialise sur l'instance. Un `scan_city` qui sort avant (aucun ancrage) pose bien un dictionnaire d'instance, mais toute lecture avant le premier scan voit l'état partagé de la classe. Sans effet aujourd'hui (instances à usage unique), fragile si le scraper est réutilisé.
- Piste : le créer dans `__init__`.
