import time
import re
import urllib.parse
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

class CityFinder:
    @staticmethod
    def find_city_id_and_coords(scraper, city_name, region_hint=None):
        """`region_hint` (optionnel) : région/pays déjà confirmé par l'utilisateur (ex: "Québec,
        Canada", venant de la sélection Nominatim côté frontend) — sert à choisir la BONNE
        suggestion parmi celles proposées par l'auto-complétion Facebook plutôt que de cliquer
        aveuglément la première (2026-08-26 : un `city_id` Facebook s'est révélé être un homonyme
        hors Québec, jamais détecté puisque `.first` ne compare jamais le texte des suggestions).
        Sans indice (repli historique, ex: villes ajoutées avant ce correctif), comportement
        inchangé : première suggestion.

        Retourne (city_id, city_coords, matched_label, matched_confidently) — `matched_label` est
        le texte de la suggestion réellement cliquée (utile pour logger/comparer même quand
        `city_coords` est absent, ce qui est le cas la majorité du temps) ; `matched_confidently`
        est `True` seulement si `region_hint` était fourni ET qu'une suggestion le contenait
        explicitement — sert à décider si la ville doit être marquée `needsReview`."""
        scraper._ensure_session()
        page = scraper.context.new_page()
        city_id = None
        city_coords = None
        matched_label = None
        matched_confidently = False
        
        try:
            scraper.logger.info(f"Début de la recherche d'ID et de coordonnées pour la ville: '{city_name}'")
            page.goto("https://www.facebook.com/marketplace/", timeout=30000)
            scraper.logger.info("Page Marketplace chargée.")

            scraper._close_login_popup(page)

            # Clic sur le bouton de localisation
            loc_button = page.locator("div[role='button']").filter(has_text=re.compile(r"\d+\s*(km|mi)", re.IGNORECASE)).first
            if not loc_button.is_visible(timeout=5000):
                scraper.logger.warning("Bouton de localisation principal non trouvé, essai d'une autre stratégie.")
                loc_button = page.locator("div[aria-label*='Lieu'], div[aria-label*='Location'], div[aria-label*='Lugar']").first
            
            if not loc_button.is_visible(timeout=3000):
                 # Fallback sur une icône de map ou un texte spécifique
                 loc_button = page.locator("i[style*='map-pin'], div:has-text('km')").last
                 scraper.logger.error("Bouton de localisation introuvable. Abandon.")
                 return None, None, None, False

            scraper.logger.info("Bouton de localisation trouvé. Clic.")
            loc_button.click(force=True)

            # Attente du dialogue
            page.wait_for_selector("div[role='dialog']", timeout=8000)
            scraper.logger.info("Dialogue de localisation ouvert.")

            # Remplissage du champ
            input_loc = page.locator("input[aria-label='Lieu'], input[aria-label='Location'], input[placeholder*='Lieu'], input[placeholder*='Location']").first
            input_loc.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            input_loc.fill(city_name)
            scraper.logger.info(f"Champ rempli avec '{city_name}'.")
            time.sleep(3) # Attente accrue des suggestions pour les connexions lentes ou villes lointaines

            # Sélection de la suggestion : par correspondance avec `region_hint` si fourni
            # (parcourt TOUTES les suggestions, pas seulement la première), sinon repli sur la
            # première comme avant.
            suggestions = page.locator("div[role='option']").all()
            if not suggestions:
                scraper.logger.warning("Aucune suggestion de ville trouvée. Tentative avec la touche Entrée.")
                page.keyboard.press("Enter")
            else:
                chosen = suggestions[0]
                matched_label = chosen.inner_text()
                if region_hint:
                    hint_norm = region_hint.strip().lower()
                    for suggestion in suggestions:
                        text = suggestion.inner_text()
                        if hint_norm in text.strip().lower():
                            chosen = suggestion
                            matched_label = text
                            matched_confidently = True
                            break
                    if not matched_confidently:
                        scraper.logger.warning(
                            f"Aucune suggestion Facebook ne correspond à l'indice de région '{region_hint}' "
                            f"parmi {len(suggestions)} proposée(s) — repli sur la première ('{matched_label}'), "
                            f"à vérifier manuellement (needsReview)."
                        )
                scraper.logger.info(f"Clic sur la suggestion : {matched_label}")
                chosen.click()
            
            time.sleep(0.5)

            # Clic sur Appliquer
            apply_btn = page.locator("div[aria-label='Appliquer'], div[aria-label='Apply']").first
            scraper.logger.info("Clic sur le bouton Appliquer.")
            apply_btn.click()

            # Attente du changement d'URL
            try:
                page.wait_for_url(re.compile(r"/marketplace/.*?/"), timeout=10000)
                current_url = page.url
                scraper.logger.info(f"Nouvelle URL: {current_url}")
                # Le format peut être /marketplace/123/ ou /marketplace/nom-ville/
                # On essaie de capturer l'ID numérique en priorité
                match = re.search(r"/marketplace/(\d+)/", current_url)
                if match:
                    city_id = match.group(1)
                else:
                    # Si pas d'ID numérique, on prend le segment de l'URL comme fallback
                    segments = current_url.split('/marketplace/')[1].split('/')
                    if segments:
                        city_id = segments[0]
                
                if city_id:
                    scraper.logger.info(f"ID ou Alias de la ville trouvé: {city_id}")
                    
                    # --- Extraction des coordonnées de l'URL ---
                    parsed_url = urllib.parse.urlparse(current_url)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    
                    lat = query_params.get('latitude')
                    lon = query_params.get('longitude')
                    
                    if lat and lon:
                        try:
                            city_coords = {'lat': float(lat[0]), 'lon': float(lon[0])}
                            scraper.logger.info(f"Coordonnées de la ville trouvées dans l'URL: {city_coords}")
                        except ValueError:
                            scraper.logger.warning("Impossible de convertir latitude/longitude en float.")
            except PlaywrightTimeoutError:
                scraper.logger.error("L'URL n'a pas changé après l'application de la nouvelle ville.")

        except Exception as e:
            scraper.logger.critical(f"Erreur critique dans CityFinder: {e}", exc_info=True)
            try:
                # Tentative de prendre une capture d'écran pour le débogage
                screenshot_path = f"city_finder_error_{time.time()}.png"
                page.screenshot(path=screenshot_path)
                scraper.logger.info(f"Capture d'écran de l'erreur enregistrée dans {screenshot_path}")
            except Exception as screenshot_error:
                scraper.logger.error(f"Impossible de prendre une capture d'écran: {screenshot_error}")
        finally:
            scraper.logger.info("Fermeture de la page CityFinder.")
            page.close()
            
        return city_id, city_coords, matched_label, matched_confidently
