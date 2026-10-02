import contextvars
from backend import llm_usage
import json
import threading
import time
import requests
import logging
from io import BytesIO
from PIL import Image
import google.generativeai as genai
from config import (
    GEMINI_API_KEY,
    DEFAULT_MAIN_PROMPT,
    DEFAULT_GATEKEEPER_INSTRUCTION,
    DEFAULT_ANALYST_INSTRUCTION,
    DEFAULT_EXPERT_CONTEXT,
    DEFAULT_SOLD_BACKFILL_INSTRUCTION,
    DEFAULT_TAXONOMY,
    DEFAULT_FEW_SHOT_EXAMPLES,
    DEFAULT_REJECTION_VERDICTS,
    DEFAULT_PRO_PRICE_THRESHOLD,
    DEFAULT_PRO_DEAL_SCORE_THRESHOLD,
    DEFAULT_PRO_COMBINED_DEAL_SCORE,
    DEFAULT_PRO_RESTO_SCORE_THRESHOLD,
    DEFAULT_PRO_AUTH_SCORE_THRESHOLD,
    DEFAULT_PRO_CONFIDENCE_THRESHOLD,
    T1_OBSERVATION_ENABLED,
    T1_GATEKEEPER_PROVIDER,
    T1_PROVIDER_CHAIN,
    T1_KNOWLEDGE_ENABLED,
    T1_KNOWLEDGE_VERSION,
    T1_KNOWLEDGE_MAX_FICHES,
    T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    T1_CIRCUIT_BREAKER_COOLDOWN_SECONDS,
)
from backend import t1_circuit_breaker
from backend import guitar_knowledge
from backend.llm_clients import (  # noqa: F401  (T1_* ré-exportées pour les scripts/tests existants)
    LLMClientsMixin,
    T1_VALID_STATUSES,
    T1_GATEKEEPER_RESPONSE_SCHEMA,
    T1_GATEKEEPER_OPENAI_JSON_SCHEMA,
)

from backend.t1_prompt import build_t1_gatekeeper_prompt, format_user_correction
from backend.scraping.parser import ListingParser
from backend.taxonomy import (
    build_index as build_taxonomy_index,
    canonicalize as canonicalize_classification,
    matches_active_search_family,
)

logger = logging.getLogger(__name__)

# Regroupe les 5 verdicts T1 "d'opportunité" (par opposition à FAIR/BAD_DEAL, "sans intérêt") —
# utilisé par `backend/scripts/audit_rejected_gems.py` (comparaison Qwen/Gemini, désaccord
# pépite-tier au sens large), PAS par le routage `activeSearchFamilies` ci-dessous (voir
# T1_FILTER_BYPASS_VERDICTS, volontairement plus restreint depuis le 2026-09-29).
T1_PEPITE_TIER_VERDICTS = frozenset({"PEPITE", "FAST_FLIP", "LUTHIER_PROJ", "CASE_WIN", "COLLECTION"})

# Rattrapage Chantier G (2026-09-19), restreint le 2026-09-29 (retour utilisateur) : SEUL le
# verdict PEPITE littéral (pas les 4 autres verdicts d'opportunité T1_PEPITE_TIER_VERDICTS) est
# jamais caché par le routage `activeSearchFamilies`, quelle que soit la correspondance de
# classification — garde-fou non négociable, ne jamais masquer une pépite hors-filtre. Décision
# explicite : un catalogue partagé entre utilisateurs (chacun avec son propre filtre) couvre déjà
# les autres verdicts d'opportunité (FAST_FLIP/LUTHIER_PROJ/CASE_WIN/COLLECTION) pour un
# utilisateur dont le filtre les inclut — pas besoin qu'ils percent AUSSI le filtre explicite d'un
# utilisateur qui les a délibérément exclus (ex: un ampli FAST_FLIP alors que la recherche active
# ne porte que sur des petites guitares acoustiques).
T1_FILTER_BYPASS_VERDICTS = frozenset({"PEPITE"})

# Verdicts d'erreur du Portier (appel raté ou réponse malformée) — n'ont par définition aucune
# classification fiable, donc jamais soumis au routage Chantier G (`activeSearchFamilies`) au
# risque d'être routés à tort vers NOT_PROMOTED. Depuis le 2026-09-24, ces verdicts font sauter
# l'annonce (retentée au prochain cycle de scan, voir GATEKEEPER_FAILED_SKIP) au lieu du fail-open
# historique vers l'Analyste (Chantier H, porté depuis dev le 2026-09-22) — provisoire, en
# attendant un vrai mécanisme de repli (ex: second appel Gemini).
T1_ERROR_STATUSES = frozenset({"ERROR", "ERROR_GATEKEEPER"})

def expert_trigger_reason(config, result_t2, numeric_price, force_expert=False):
    """Motif de déclenchement de l'Expert Pro (Tier 3) d'après le résultat de l'Analyste (Tier 2),
    ou None s'il n'est pas déclenché. Fonction pure (aucune E/S, aucun logger) : extraite de
    `_run_analysis_cascade_body` pour être testable seule. L'ORDRE des conditions fait foi (la
    première qui correspond gagne) ; seuils lus dans `config` avec les défauts `DEFAULT_PRO_*`."""
    deal_score = result_t2.get('deal_score', 0)
    auth_score = result_t2.get('authenticity_score', 10)  # 10 par défaut pour ne pas trigger faussement
    resto_score = result_t2.get('restoration_interest_score', 0)
    confidence = result_t2.get('confidence', 1.0)
    verdict = result_t2.get('verdict', '')

    if force_expert:
        return "Analyse Pro forcée manuellement"
    if numeric_price > config.get('proTriggerPriceThreshold', DEFAULT_PRO_PRICE_THRESHOLD) and deal_score >= 4:
        return f"Prix élevé ({numeric_price}) avec score correct ({deal_score})"
    if deal_score >= config.get('proTriggerDealScoreThreshold', DEFAULT_PRO_DEAL_SCORE_THRESHOLD):
        return f"Score attractivité critique ({deal_score})"
    if (deal_score >= config.get('proTriggerCombinedDealScore', DEFAULT_PRO_COMBINED_DEAL_SCORE)
            and resto_score >= config.get('proTriggerRestoScoreThreshold', DEFAULT_PRO_RESTO_SCORE_THRESHOLD)):
        return f"Combo Jackpot : Score correct ({deal_score}) + Restaurabilité majeure ({resto_score})"
    if auth_score <= config.get('proTriggerAuthScoreThreshold', DEFAULT_PRO_AUTH_SCORE_THRESHOLD):
        return f"Doute authenticité potentiel ({auth_score})"
    if confidence < config.get('proTriggerConfidenceThreshold', DEFAULT_PRO_CONFIDENCE_THRESHOLD):
        return f"Faible confiance T2 ({confidence})"
    if verdict == 'COLLECTION':
        return "Verdict COLLECTION (Double validation requise)"
    return None


class DealAnalyzer(LLMClientsMixin):
    def __init__(self, logger: logging.Logger = None):
        self.models = {}
        self._model_error_last_notified = {}
        # Index de taxonomie mémorisé : `canonicalize()` le reconstruisait pour CHAQUE annonce
        # analysée (200 nœuds parcourus à chaque fois) alors qu'il ne change qu'avec la config.
        self._taxonomy_index = None
        self._taxonomy_index_source = None
        # Chantier H (porté 2026-09-22) : `bot.py::_dispatch_analysis_batch` appelle désormais
        # cette même instance depuis plusieurs threads worker en parallèle (avant, un seul thread
        # par utilisateur appelait `analyze_deal` séquentiellement) — `self.models`/
        # `self._taxonomy_index` sont de simples caches "vérifier-puis-écrire" jamais protégés
        # jusqu'ici. Un seul verrou pour les deux : leur construction est rapide et purement
        # locale (aucun appel réseau tenu sous le verrou), donc pas de risque de contention
        # significative ni de deadlock croisé.
        self._cache_lock = threading.Lock()
        # Logger par-utilisateur (Firestore/LogViewer) injecté par bot.py ; repli sur le
        # logger de module si non fourni (scripts autonomes/tests).
        self.logger = logger or logging.getLogger(__name__)
        if not GEMINI_API_KEY:
            self.logger.warning("⚠️ Pas de clé API Gemini fournie.")
            return
        
        genai.configure(api_key=GEMINI_API_KEY)
        try:
            model_list = [f"ID: {m.name} | Display Name: {m.display_name}" for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            self.logger.info("--- Modèles Gemini Disponibles ---\n" + "\n".join(model_list))
        except Exception as e:
            self.logger.critical(f"CRITICAL: Impossible de lister les modèles Gemini : {e}", exc_info=True)


    def _download_and_optimize_image(self, url, max_size=2048):
        try:
            if not url or "via.placeholder.com" in url: return None
            response = requests.get(url, timeout=10)
            if response.status_code != 200: return None
            
            img = Image.open(BytesIO(response.content))
            if img.size[0] > max_size or img.size[1] > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            return img.convert("RGB") if img.mode in ("RGBA", "P") else img
        except Exception as e:
            self.logger.warning(f"⚠️ Impossible de traiter l'image {url}: {e}")
            return None


    def _construct_base_user_prompt(self, listing_data, main_prompt_template, taxonomy_data, few_shot_examples=None):
        """Construit le prompt utilisateur de base (DRY)"""
        prompt_lines = main_prompt_template if isinstance(main_prompt_template, list) else str(main_prompt_template).split('\n')
        main_prompt_str = "\n".join(prompt_lines)
        
        examples_str = ""
        if few_shot_examples:
            examples_lines = few_shot_examples if isinstance(few_shot_examples, list) else str(few_shot_examples).split('\n')
            examples_str = "\n".join(examples_lines) + "\n\n"

        # sort_keys=True : garantit un préfixe identique octet pour octet entre threads/
        # redémarrages (le cache implicite Gemini est un match de préfixe exact) — sans ça,
        # l'ordre des clés d'un dict Python n'est pas garanti stable d'un process à l'autre.
        taxonomy_str = json.dumps(taxonomy_data, indent=2, ensure_ascii=False, sort_keys=True)

        return (
            f"{main_prompt_str}\n\n"
            f"### TAXONOMIE DE RÉFÉRENCE\n"
            f"{taxonomy_str}\n\n"
            f"{examples_str}"
            f"Détails de l'annonce :\n"
            f"- Titre : {listing_data.get('title', 'N/A')}\n"
            f"- Prix : {listing_data.get('price', 'N/A')}\n"
            f"- Description : {listing_data.get('description', 'N/A')}\n"
            f"- Localisation : {listing_data.get('location', 'N/A')}\n"
        )

    @staticmethod
    def _format_user_correction(user_comment):
        """Délègue à `backend/t1_prompt.py` (source unique du texte de correction, partagé entre
        le prompt T1 et `base_prompt` T2/T3 — les deux appelants le PLACENT différemment)."""
        return format_user_correction(user_comment)

    def _t1_knowledge(self, listing_data):
        """Base de connaissances « univers des guitares » pour le Portier : renvoie `(bloc_prompt, trace)`.
        `("", {})` si l'interrupteur `T1_KNOWLEDGE_ENABLED` est éteint (défaut : AUCUN accès base, prompt inchangé),
        si aucune fiche ne correspond, ou si quoi que ce soit échoue — ÉCHEC OUVERT : la base ne doit jamais
        empêcher une analyse (le Portier tourne alors comme avant). `trace` (`gatekeeperKnowledge` : version de la
        base, ids et alias trouvés) est stockée avec la décision (`ai_analysis_raw`) pour attribuer un changement
        de comportement à une version de la base. Les sources (URL) ne sont jamais injectées."""
        if not T1_KNOWLEDGE_ENABLED:
            return "", {}
        try:
            from backend import pg_db
            guitar_knowledge.configure_version(T1_KNOWLEDGE_VERSION)      # idempotent
            with pg_db.get_pool().connection(timeout=1.0) as conn:
                fiches = guitar_knowledge.lookup(conn, listing_data.get("title"), listing_data.get("description"),
                                                 limit=T1_KNOWLEDGE_MAX_FICHES)
                version = guitar_knowledge.effective_version(conn)
            if not fiches:
                return "", {}
            trace = {"gatekeeperKnowledge": {"version": version,
                                             "fiches": [f["id"] for f in fiches],
                                             "matched": [f["matched_on"] for f in fiches]}}
            return guitar_knowledge.format_for_prompt(fiches), trace
        except Exception as e:  # jamais bloquant
            self.logger.warning(f"⚠️ [Portier] base de connaissances indisponible, analyse sans elle : {e}")
            return "", {}

    def _construct_t1_gatekeeper_prompt(self, listing_data, taxonomy_data, gatekeeper_instruction, user_comment=None,
                                        knowledge_block=""):
        """Prompt du Portier (T1) — délibérément séparé de `_construct_base_user_prompt` (celui-ci
        reste réservé à T2/T3). Décision utilisateur du 2026-09-29 : bascule en prod du "prompt
        simplifié" validé sur 665 annonces (JOURNAL.md, Chantier I). Implémentation et historique
        de conception dans `backend/t1_prompt.py` (source unique, aussi utilisée par
        `backend/scripts/compare_qwen_local_vs_prod.py`)."""
        return build_t1_gatekeeper_prompt(listing_data, taxonomy_data, gatekeeper_instruction, user_comment,
                                          knowledge_block)








    def _run_t1_shadow_observation(self, full_prompt_t1, images, shadow_provider, gatekeeper_model_name, user_email=None):
        """Chantier H (porté depuis dev le 2026-09-22) — OBSERVATION EN MIROIR : rejoue le
        Portier avec EXACTEMENT le même prompt sur le fournisseur T1 qui N'EST PAS le décideur
        réel (`T1_GATEKEEPER_PROVIDER`), pour continuer à accumuler de la comparaison en
        conditions réelles après la bascule — n'influence JAMAIS `gatekeeper_status` ni la
        décision accept/reject réelle. Décideur "qwen" (défaut) -> observation sous
        `flashliteGatekeeper*` ; décideur "gemini" (repli) -> observation sous `qwenGatekeeper*`.

        Best-effort strict : toute erreur (clé absente, fournisseur indisponible, JSON invalide)
        est absorbée ici et ne doit jamais faire échouer l'analyse réelle qui l'entoure —
        coupe-circuit `T1_OBSERVATION_ENABLED` pour désactiver sans redéploiement si besoin.
        """
        if not T1_OBSERVATION_ENABLED:
            return {}
        prefix = "qwenGatekeeper" if shadow_provider == "qwen" else "flashliteGatekeeper"
        t0 = time.monotonic()
        result, err = self._call_t1_provider(shadow_provider, full_prompt_t1, images, gatekeeper_model_name, user_email, action="t1_shadow")
        latency_s = round(time.monotonic() - t0, 1)
        if err or not result:
            self.logger.warning(f"   🔬 [Observation T1/{shadow_provider}] échec (ignoré, n'affecte pas l'analyse) : {err}")
            return {f"{prefix}Error": err, f"{prefix}LatencyS": latency_s}
        return {
            f"{prefix}Verdict": (result.get('status') or result.get('verdict') or None),
            f"{prefix}Brand": result.get('brand'),
            f"{prefix}Classification": result.get('classification'),
            f"{prefix}LatencyS": latency_s,
        }

    def analyze_deal(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Cascade 3-Tiers, puis canonicalisation de la classification renvoyée par l'IA.

        La canonicalisation est faite ICI, sur le résultat final, plutôt que dans chacun des 5
        points de sortie de la cascade : un seul endroit à maintenir, impossible d'en oublier un.
        """
        llm_usage.current_deal_id.set(listing_data.get('id'))
        llm_usage.current_user_ref.set(user_email)
        result = self._run_analysis_cascade(listing_data, firestore_config, force_expert, user_comment, user_email)
        taxonomy = (firestore_config or {}).get('analysisConfig', {}).get('taxonomy', DEFAULT_TAXONOMY)
        return self._canonicalize_classification(result, taxonomy)

    def analyze_deal_light(self, listing_data, firestore_config=None, user_email=None):
        """Backfill léger : reconstitue UNIQUEMENT les champs structurés (scores/classification/
        marge/verdict) d'une annonce déjà VENDUE dont `aiAnalysis` a été perdu (bug `ArrayUnion`
        de `mark_deal_as_sold()`, corrigé le 2026-08-12 — voir JOURNAL.md), sans repasser par le
        Portier T1 (inutile : l'annonce est déjà vendue, pas besoin de la re-filtrer) ni risquer de
        déclencher l'Expert Pro T3 (coûteux, inutile pour de l'historique déjà écoulé). Un seul
        appel au modèle Analyste T2, avec une instruction dédiée (`sold_backfill_instruction`)
        demandant un JSON réduit sans champ de texte libre (pas de `analysis`/`reasoning`/
        `summary`/`visual_inspection`) — économise à la fois des appels entiers (T1, risque T3) et
        des tokens de sortie par appel, par rapport à `analyze_deal()`. Utilisé par
        `backend/scripts/backfill_sold_scores.py`.

        `model_used` est tagué `"backfill_leger -> {modèle}"` (2 maillons) plutôt qu'un simple nom
        de modèle : `StatsView.jsx::modelChainTokens` compte les maillons pour détecter qu'une
        annonce a atteint le Tier 2 (`length >= 2`) — un maillon unique ferait sous-compter ces
        annonces dans le Funnel alors qu'elles ont bien été scorées.
        """
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        llm_usage.current_deal_id.set(listing_data.get('id'))
        llm_usage.current_user_ref.set(user_email)
        config = (firestore_config or {}).get('analysisConfig', {})
        analyst_model_name = config.get('mainModel', 'gemini-3.7-flash')
        taxonomy = config.get('taxonomy', DEFAULT_TAXONOMY)
        few_shot_examples = config.get('fewShotExamples', DEFAULT_FEW_SHOT_EXAMPLES)

        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        base_prompt = self._construct_base_user_prompt(
            listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), taxonomy, few_shot_examples
        )
        backfill_instruction = config.get('soldBackfillInstruction', DEFAULT_SOLD_BACKFILL_INSTRUCTION)
        if isinstance(backfill_instruction, list):
            backfill_instruction = "\n".join(backfill_instruction)
        full_prompt = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE BACKFILL (VENTE HISTORIQUE) ---\n{backfill_instruction}"

        self.logger.info(f"   🩹 Backfill léger ({analyst_model_name}) : {listing_data.get('title', 'Inconnu')}")
        result, err = self._call_gemini_json(analyst_model_name, [full_prompt] + images, user_email, action="t2_backfill_light")
        if err or not result:
            return {"verdict": "ERROR", "reasoning": f"Erreur backfill léger : {err}", "model_used": f"backfill_leger -> {analyst_model_name} (Error)"}

        result["model_used"] = f"backfill_leger -> {analyst_model_name}"
        return self._canonicalize_classification(result, taxonomy)

    def _get_taxonomy_index(self, taxonomy):
        """Index de taxonomie mémorisé, reconstruit uniquement si la taxonomie a changé.

        Comparaison par identité : `ConfigManager` réutilise le même objet de configuration entre
        deux analyses, donc l'index n'est reconstruit qu'après une vraie modification de la config
        (et une comparaison par identité qui échouerait à tort ne coûterait qu'une reconstruction,
        jamais un résultat faux). Verrouillé (`_cache_lock`, partagé avec `_get_model`) depuis que
        plusieurs workers peuvent appeler cette méthode en parallèle (Chantier H, porté
        2026-09-22) : sans ça, deux threads pourraient interfolier lecture/écriture de
        `_taxonomy_index`/`_taxonomy_index_source`.
        """
        with self._cache_lock:
            if self._taxonomy_index is None or self._taxonomy_index_source is not taxonomy:
                self._taxonomy_index = build_taxonomy_index(taxonomy)
                self._taxonomy_index_source = taxonomy
            return self._taxonomy_index

    def _canonicalize_classification(self, result, taxonomy):
        """Remplace `classification` par son chemin canonique complet, ou la retire si invalide.

        Le prompt EXIGE désormais un chemin complet, mais le prompt ne garantit rien (aucun
        `response_schema` côté SDK) : cette validation serveur est le vrai garde-fou. Une valeur
        ambiguë ou inconnue est écartée plutôt que stockée telle quelle — une annonce non classée
        est corrigeable à la main dans l'app, une annonce rangée dans la mauvaise catégorie passe
        inaperçue (c'est ainsi que des étuis se retrouvaient comptés comme des guitares).
        """
        if not isinstance(result, dict):
            return result

        raw = result.get('classification')
        if not raw:
            return result

        canonical, reason = canonicalize_classification(raw, taxonomy, self._get_taxonomy_index(taxonomy))
        if canonical:
            if canonical != raw:
                self.logger.info(f"   🧭 Classification normalisée : '{raw}' -> '{canonical}' ({reason})")
            result['classification'] = canonical
        else:
            self.logger.warning(
                f"   ⚠️ Classification rejetée ('{raw}', {reason}) : absente de la taxonomie ou "
                f"ambiguë (nom porté par plusieurs branches). L'annonce restera non classée — "
                f"corrigeable manuellement depuis la fiche."
            )
            result['classification'] = None
            result['classification_rejected'] = raw

        return result

    def _attach_gatekeeper_metadata(self, result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation):
        """Rattrapage Chantier G (2026-09-19) : attache marque/classification/verdict BRUTS du
        Portier à `result`, en place, et le retourne — nécessaires pour retrouver, sans rappeler
        le Portier, la classification d'une annonce `NOT_PROMOTED` quand le filtre
        `activeSearchFamilies` change (voir `bot.py::reevaluate_not_promoted`). `qwen_observation`
        (Chantier H, porté depuis dev le 2026-09-22) : merge l'observation miroir best-effort
        (`flashliteGatekeeper*`/`qwenGatekeeper*`, voir `_run_t1_shadow_observation`) — jamais
        utilisée pour la décision réelle. Stockée sans colonne Postgres dédiée : `result` devient
        `analysis_data`, qui atterrit tel quel dans `ai_analysis_raw` (JSONB, voir
        `deal_mapping.py::map_deal`) — aucune promotion de colonne nécessaire pour des champs
        purement d'observation, jamais lus par le frontend."""
        result["gatekeeperBrand"] = gatekeeper_brand
        result["gatekeeperClassification"] = gatekeeper_classification
        result["gatekeeperVerdict"] = gatekeeper_status
        result.update(qwen_observation)
        return result

    def _run_analysis_cascade(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Point d'entrée public : point de sortie UNIQUE pour l'attache des métadonnées Portier
        (`_attach_gatekeeper_metadata`), quel que soit le chemin emprunté par `_run_analysis_cascade_body`
        (rejet T1, hors-recherche-active, erreur T2, échec T3 avec repli T2, succès T2/T3) — un futur
        point de sortie ajouté au corps de la cascade n'a qu'à retourner le même tuple `(result,
        gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)`, l'attache
        elle-même ne peut plus être oubliée à un site d'appel particulier (rattrapage Chantier G,
        2026-09-19)."""
        if not GEMINI_API_KEY:
            return {"verdict": "ERROR", "reasoning": "La clé API Gemini n'est pas configurée."}

        result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation = self._run_analysis_cascade_body(
            listing_data, firestore_config, force_expert, user_comment, user_email,
        )
        return self._attach_gatekeeper_metadata(
            result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation
        )

    def _run_analysis_cascade_body(self, listing_data, firestore_config=None, force_expert=False, user_comment=None, user_email=None):
        """Corps de la cascade 3-Tiers — chaque point de sortie retourne
        `(result, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)`,
        jamais un dict déjà attaché (voir `_run_analysis_cascade`, seul appelant, qui fait
        l'attache une fois pour tous les chemins)."""
        config = firestore_config.get('analysisConfig', {})
        # Défauts alignés sur GEMINI_MODELS (config.py) — gemini-2.5-* est retiré par Google en
        # octobre 2026, ces fallbacks codés en dur sont ce qui est réellement utilisé si un compte
        # n'a jamais persisté sa config (voir CLAUDE.md § Points d'Attention Critiques).
        gatekeeper_model_name = config.get('gatekeeperModel', 'gemini-3.5-flash-lite')
        analyst_model_name = config.get('mainModel', 'gemini-3.7-flash')
        # Rétrocompatibilité : 'proModel' est la nouvelle clé, 'expertModel' est l'ancienne (encore écrite par le frontend)
        expert_pro_model_name = config.get('proModel') or config.get('expertModel', 'gemini-3.1-pro-preview')

        taxonomy = config.get('taxonomy', DEFAULT_TAXONOMY)
        few_shot_examples = config.get('fewShotExamples', DEFAULT_FEW_SHOT_EXAMPLES)
        rejection_verdicts = config.get('rejectionVerdicts', DEFAULT_REJECTION_VERDICTS)

        self.logger.info(f"🤖 Analyse Cascade pour : {listing_data.get('title', 'Inconnu')} (Force Expert: {force_expert})")

        # Téléchargement des images
        image_urls = (listing_data.get('imageUrls') or [listing_data.get('imageUrl')])[:8]
        images = [img for url in image_urls if (img := self._download_and_optimize_image(url))]

        # 1. Construction du Prompt de Base (DRY : Fait une seule fois)
        base_prompt = self._construct_base_user_prompt(listing_data, config.get('mainAnalysisPrompt', DEFAULT_MAIN_PROMPT), taxonomy, few_shot_examples)
        if user_comment:
            base_prompt += f"\n\n{self._format_user_correction(user_comment)}"

        model_chain = []
        gatekeeper_status = "MANUAL_RETRY"
        gatekeeper_reason = "Analyse experte demandée manuellement."
        gatekeeper_brand = None
        gatekeeper_classification = None
        # Chantier H (porté depuis dev le 2026-09-22) — observation miroir (jamais utilisée pour
        # la décision accept/reject réelle, voir _run_t1_shadow_observation). Fusionnée dans les 5
        # dicts de retour ci-dessous via _attach_gatekeeper_metadata, comme gatekeeperBrand/
        # gatekeeperClassification/gatekeeperVerdict.
        qwen_observation = {}

        # ==========================================
        # PHASE 1 : TIER 1 - PORTIER (Chantier I, 2026-09-29 : chaîne T1_PROVIDER_CHAIN — local Dell
        # primaire / Qwen cloud secours par défaut, voir config.py)
        # ==========================================
        if not force_expert:
            self.logger.info(f"   🛡️ Étape 1 : Portier (chaîne {' -> '.join(T1_PROVIDER_CHAIN)})")
            gatekeeper_instruction = config.get('gatekeeperVerbosityInstruction', DEFAULT_GATEKEEPER_INSTRUCTION)
            if isinstance(gatekeeper_instruction, list):
                gatekeeper_instruction = "\n".join(gatekeeper_instruction)
            # Prompt simplifié (2026-09-29, décision utilisateur — voir _construct_t1_gatekeeper_prompt) :
            # n'est PLUS basé sur base_prompt (réservé à T2/T3 ci-dessus) — la correction utilisateur
            # (flux "Ré-analyser" sans Force Expert, rare mais possible, voir bot.py::analyze_single_deal)
            # est passée directement pour être placée AVANT `<annonce>`, jamais après (voir docstring).
            knowledge_block, knowledge_trace = self._t1_knowledge(listing_data)
            full_prompt_t1 = self._construct_t1_gatekeeper_prompt(listing_data, taxonomy, gatekeeper_instruction, user_comment,
                                                                  knowledge_block)

            # Observation miroir Chantier H (Qwen vs Gemini) : conservée telle quelle, ORTHOGONALE
            # à la chaîne T1_PROVIDER_CHAIN — toujours sur l'opposé de T1_GATEKEEPER_PROVIDER, quel
            # que soit le fournisseur qui décidera réellement ci-dessous (y compris "local"), pour
            # continuer à accumuler la comparaison historique Qwen/Gemini sans dépendre du résultat
            # de la chaîne. Lancée en parallèle pour ne pas cumuler les latences sur chaque annonce.
            shadow_provider = "gemini" if T1_GATEKEEPER_PROVIDER == "qwen" else "qwen"

            shadow_result_holder = [{}]

            def _observe_shadow():
                shadow_result_holder[0] = self._run_t1_shadow_observation(
                    full_prompt_t1, images, shadow_provider, gatekeeper_model_name, user_email
                )

            shadow_thread = threading.Thread(target=contextvars.copy_context().run, args=(_observe_shadow,), daemon=True)
            shadow_thread.start()

            # Chantier I : essaie chaque fournisseur de T1_PROVIDER_CHAIN dans l'ordre. Un
            # fournisseur en pause (coupe-circuit, voir t1_circuit_breaker.py) est sauté sans être
            # appelé. Deux échecs distincts :
            # - ERREUR RÉELLE (candidate_err) : appel raté (réseau, auth, JSON invalide...) — DÉJÀ
            #   enregistré dans `llm_usage` (ok=False, error_type) par l'appelé
            #   (`_call_openai_compatible_json`/`_call_gemini_json`), ne PAS le ré-enregistrer ici
            #   (double comptage) ; compte seulement pour le coupe-circuit.
            # - RÉPONSE VIDE SANS ERREUR (`{}`, ex: JSON normalisé depuis un tableau vide) : l'appel
            #   a réussi et est DÉJÀ enregistré ok=True par l'appelé (tokens réels facturés) — ne
            #   pas ré-enregistrer ok=False dessus (double comptage) ni compter comme panne pour le
            #   coupe-circuit (le fournisseur a bien répondu, c'est un problème de qualité de
            #   réponse, pas de disponibilité) : on essaie juste le candidat suivant.
            # L'annonce n'est sautée (retentée au prochain cycle) que si TOUTE la chaîne échoue.
            result_t1, primary_provider = None, None
            tried, chain_errors = [], []
            for candidate in T1_PROVIDER_CHAIN:
                if t1_circuit_breaker.is_open(candidate):
                    self.logger.warning(f"   ⏸️ [Portier/{candidate}] en pause (coupe-circuit) — passage au suivant.")
                    continue
                tried.append(candidate)
                candidate_result, candidate_err = self._call_t1_provider(
                    candidate, full_prompt_t1, images, gatekeeper_model_name, user_email
                )
                if candidate_err:
                    t1_circuit_breaker.record_failure(
                        candidate, T1_CIRCUIT_BREAKER_FAILURE_THRESHOLD, T1_CIRCUIT_BREAKER_COOLDOWN_SECONDS
                    )
                    # L'échec est déjà enregistré dans `llm_usage` (ok=False + error_type) par l'appelé
                    # (`_call_openai_compatible_json`/`_call_gemini_json`), une ligne par tentative.
                    self.logger.warning(f"   ⚠️ [Portier/{candidate}] échec — {candidate_err}")
                    chain_errors.append(f"{candidate}: {candidate_err}")
                    continue
                if not candidate_result:
                    self.logger.warning(f"   ⚠️ [Portier/{candidate}] réponse vide — passage au suivant.")
                    chain_errors.append(f"{candidate}: réponse vide")
                    continue
                t1_circuit_breaker.record_success(candidate)
                result_t1, primary_provider = candidate_result, candidate
                break

            t1_real_model_name = (
                self._t1_model_name_for(primary_provider, gatekeeper_model_name) if primary_provider
                else "/".join(self._t1_model_name_for(p, gatekeeper_model_name) for p in (tried or T1_PROVIDER_CHAIN))
            )
            model_chain.append(t1_real_model_name)

            shadow_thread.join()
            qwen_observation = {**shadow_result_holder[0], **knowledge_trace}   # + traçabilité de la base de connaissances

            if not result_t1:
                # Skip (2026-09-24, chaîne Chantier I depuis le 2026-09-29) : un échec de TOUTE la
                # chaîne T1_PROVIDER_CHAIN ne fait plus fail-open vers l'Analyste (ce qui revenait à
                # ne plus filtrer AUCUNE annonce tant que ça persistait) — l'annonce est sautée sans
                # être stockée ni marquée traitée, elle sera retentée au prochain cycle de scan
                # (voir GATEKEEPER_FAILED_SKIP plus bas, et bot.py::handle_deal_found).
                gatekeeper_status = "ERROR_GATEKEEPER"
                if chain_errors:
                    gatekeeper_reason = " | ".join(chain_errors)
                elif not T1_PROVIDER_CHAIN:
                    gatekeeper_reason = "T1_PROVIDER_CHAIN est vide — configuration invalide."
                else:
                    gatekeeper_reason = "Toute la chaîne T1_PROVIDER_CHAIN est en pause (coupe-circuit)."
                chain_label = "T1-chain(" + ",".join(tried or T1_PROVIDER_CHAIN) + ")"
                self.logger.error(f"   ❌ [Portier réel/{chain_label}] échec sur toute la chaîne — annonce sautée, sera retentée au prochain cycle : {gatekeeper_reason}")
                # Deux alertes distinctes : ne prétendre "modèle retiré" que si l'erreur y
                # ressemble vraiment (_is_model_unavailable_error) — sinon (image tronquée, panne
                # réseau/TokenRouter transitoire, etc.), une alerte honnête qui ne présume pas la
                # cause. Les deux sont throttlées séparément (clé distincte).
                if self._is_model_unavailable_error(gatekeeper_reason):
                    self._notify_model_unavailable(chain_label, gatekeeper_reason, user_email)
                else:
                    self._notify_gatekeeper_failure(chain_label, gatekeeper_reason, user_email)
            else:
                gatekeeper_status = (result_t1.get('status') or result_t1.get('verdict') or 'UNKNOWN').upper()
                gatekeeper_reason = result_t1.get('reason') or result_t1.get('reasoning') or 'Pas de raison fournie.'
                gatekeeper_brand = result_t1.get('brand')
                gatekeeper_classification = result_t1.get('classification')

                if gatekeeper_status == 'UNKNOWN':
                    gatekeeper_status = 'ERROR'
                    gatekeeper_reason = f"Réponse IA invalide. Brut : {str(result_t1)}"

                self.logger.info(f"   👉 Verdict Portier : {gatekeeper_status} ({gatekeeper_reason})")

                legacy_rejection = ['REJECTED', 'REJECTED (SERVICE)']
                if gatekeeper_status in rejection_verdicts or gatekeeper_status in legacy_rejection or gatekeeper_status.startswith('REJECTED'):
                    return (
                        {
                            "verdict": gatekeeper_status, "reasoning": gatekeeper_reason,
                            "classification": gatekeeper_classification,
                            "model_used": " -> ".join(model_chain),
                        },
                        gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
                    )

                # ==========================================
                # RATTRAPAGE CHANTIER G : ROUTAGE PAR RECHERCHE ACTIVE (promotion large)
                # ==========================================
                # Le mode par défaut ("tout analyser, filtrer après") reste inchangé tant
                # qu'aucune recherche active n'est configurée (`activeSearchFamilies` vide/absent).
                # Quand une recherche est active, seule une correspondance sur la FAMILLE de forme
                # (`gatekeeper_classification`, déjà produite par le Portier — aucun nouvel appel
                # ni champ de prompt) promeut vers T2/T3 ; le scraping et le Portier lui-même
                # continuent de tourner sur 100% des annonces, seul ce routage post-T1 change.
                # Garde-fou non négociable, restreint le 2026-09-29 : SEUL un verdict PEPITE
                # littéral (T1_FILTER_BYPASS_VERDICTS) passe TOUJOURS, correspondance ou non — ne
                # jamais cacher une vraie pépite hors-filtre. Les 4 autres verdicts d'opportunité
                # (FAST_FLIP/LUTHIER_PROJ/CASE_WIN/COLLECTION) sont désormais soumis au filtre
                # comme n'importe quel verdict ordinaire — un utilisateur qui exclut une catégorie
                # (ex: amplis) ne veut pas la voir malgré un potentiel de revente, et le catalogue
                # partagé couvre déjà cette catégorie pour un autre utilisateur dont le filtre
                # l'inclut.
                # Second garde-fou (Chantier H) : un verdict d'erreur (T1_ERROR_STATUSES — Portier
                # planté ou réponse malformée) n'a par définition aucune classification fiable ;
                # sans ce garde-fou, il se retrouverait routé vers NOT_PROMOTED (classification
                # vide ⇒ aucune correspondance) au lieu du skip dédié juste après ce bloc.
                active_search_families = config.get('activeSearchFamilies') or []
                if (
                    active_search_families
                    and gatekeeper_status not in T1_FILTER_BYPASS_VERDICTS
                    and gatekeeper_status not in T1_ERROR_STATUSES
                ):
                    matches_active_search = matches_active_search_family(gatekeeper_classification, active_search_families)
                    if not matches_active_search:
                        self.logger.info(
                            f"   🔎 Hors recherche active ({', '.join(active_search_families)}) "
                            f"et pas une pépite ({gatekeeper_status}) — non promue vers T2/T3."
                        )
                        return (
                            {
                                "verdict": "NOT_PROMOTED",
                                "reasoning": (
                                    f"Ne correspond à aucune recherche active "
                                    f"({', '.join(active_search_families)}) et n'est pas jugée "
                                    f"pépite potentielle par le Portier."
                                ),
                                "classification": gatekeeper_classification,
                                "model_used": " -> ".join(model_chain),
                            },
                            gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
                        )

            # Skip (2026-09-24, provisoire) : un Portier qui n'a produit aucun verdict fiable
            # (échec d'appel OU réponse malformée, T1_ERROR_STATUSES) ne fait plus fail-open vers
            # l'Analyste — `bot.py::handle_deal_found` reconnaît ce verdict et n'écrit rien en
            # base, l'annonce sera donc re-scrapée et retentée au prochain cycle plutôt que
            # figée avec une analyse T2 jamais filtrée par le Portier.
            if gatekeeper_status in T1_ERROR_STATUSES:
                return (
                    {
                        "verdict": "GATEKEEPER_FAILED_SKIP", "reasoning": gatekeeper_reason,
                        "classification": gatekeeper_classification,
                        "model_used": " -> ".join(model_chain),
                    },
                    gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
                )
        else:
            self.logger.info("   ⏩ Portier sauté (Force Expert).")

        # ==========================================
        # PHASE 2 : TIER 2 - ANALYSTE (Flash)
        # ==========================================
        self.logger.info(f"   🔍 Étape 2 : Analyste ({analyst_model_name}) - Structuration & Scores...")
        model_chain.append(analyst_model_name)
        analyst_instruction = config.get('analystVerbosityInstruction', DEFAULT_ANALYST_INSTRUCTION)
        if isinstance(analyst_instruction, list):
            analyst_instruction = "\n".join(analyst_instruction)
        full_prompt_t2 = f"{base_prompt}\n\n--- INSTRUCTION SPÉCIALE ANALYSTE ---\n{analyst_instruction}"

        result_t2, err_t2 = self._call_gemini_json(analyst_model_name, [full_prompt_t2] + images, user_email, action="t2_analyst")
        
        if err_t2 or not result_t2:
            return (
                {
                    "verdict": gatekeeper_status, "reasoning": f"{gatekeeper_reason}\n\nErreur Tier 2 Analyste: {err_t2}",
                    "model_used": " -> ".join(model_chain) + " (Error)",
                },
                gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation,
            )

        # Formatage des variables pour la logique conditionnelle
        deal_score = result_t2.get('deal_score', 0)
        auth_score = result_t2.get('authenticity_score', 10) # 10 par défaut pour pas trigger fausement
        resto_score = result_t2.get('restoration_interest_score', 0)
        confidence = result_t2.get('confidence', 1.0)
        verdict = result_t2.get('verdict', '')
        
        # Extraction du prix
        numeric_price = ListingParser.extract_price_from_text(str(listing_data.get('price', '') or ''))
        
        self.logger.info(f"   📊 Scores T2 -> Deal: {deal_score} | Auth: {auth_score} | Resto: {resto_score} | Conf: {confidence} | Prix: {numeric_price}")

        trigger_reason = expert_trigger_reason(config, result_t2, numeric_price, force_expert)

        # ==========================================
        # PHASE 3 : TIER 3 - EXPERT PRO (Conditionnel)
        # ==========================================
        if trigger_reason:
            self.logger.info(f"   ⭐ Étape 3 (DÉCLENCHÉE) : Expert Pro ({expert_pro_model_name}) - Motif : {trigger_reason}")
            model_chain.append(expert_pro_model_name)
            
            expert_context_raw = config.get('expertProContextInstruction', DEFAULT_EXPERT_CONTEXT)
            if isinstance(expert_context_raw, list):
                expert_context_raw = "\n".join(expert_context_raw)
            
            # Contextualisation de l'expert pro avec le json T2
            context_t3 = expert_context_raw.format(
                status=verdict,
                reasoning=result_t2.get('summary', 'Analyse rapide T2 terminée.')
            )
            
            # base_prompt avant context_t3 (et non l'inverse) : aligne T3 sur le pattern déjà
            # correct de T1/T2 (bloc statique taxonomie/prompt de base en tête, addendum
            # spécifique au Tier après) pour laisser le cache implicite Gemini matcher le
            # préfixe statique commun — l'ordre précédent plaçait le contexte T2 (dynamique,
            # différent à chaque annonce) en tête, détruisant tout préfixe cacheable pour T3.
            full_prompt_t3 = f"{base_prompt}\n\n{context_t3}"

            result_t3, err_t3 = self._call_gemini_json(expert_pro_model_name, [full_prompt_t3] + images, user_email, action="t3_expert")
            
            if err_t3 or not result_t3:
                # Ne fait plus fail-back silencieusement vers le T2 (2026-09-27, demande explicite
                # utilisateur) : un Tier 3 déclenché (auto ou Analyse Expert manuelle) doit soit
                # réussir en tant que tel, soit échouer visiblement — l'ancien repli produisait un
                # résultat quasi identique à l'analyse déjà en base (le T2 avait déjà tourné juste
                # avant), donnant l'impression trompeuse qu'une "Analyse Expert" n'avait servi à
                # rien. `_call_gemini_json` a déjà notifié _notify_model_unavailable si l'erreur y
                # ressemble (voir plus haut dans ce fichier) — pas de second appel ici.
                # L'exception remonte jusqu'à `analyze_deal()` (aucun try/except entre les deux) :
                # chaque appelant (bot.py::analyze_single_deal/process_retry_queue/
                # reevaluate_not_promoted, et _dispatch_analysis_batch pour le scan automatique) la
                # traite déjà comme un échec d'analyse (statut 'analysis_failed' / commande en
                # erreur / annonce non stockée), sans qu'aucun de ces sites n'ait besoin d'être
                # modifié pour ce changement.
                error_msg = f"Échec de l'analyse Expert Pro (Tier 3, {expert_pro_model_name}) : {err_t3 or 'réponse vide'}"
                self.logger.error(f"❌ {error_msg}")
                raise RuntimeError(error_msg)

            # L'Expert Pro écrase le T2
            result_t3["model_used"] = " -> ".join(model_chain)
            result_t3["tier3_trigger"] = trigger_reason
            self.logger.info(f"   ✅ Verdict Expert Pro : {result_t3.get('verdict', 'N/A')} | Deal: {result_t3.get('deal_score', '?')} | Auth: {result_t3.get('authenticity_score', '?')} | Conf: {result_t3.get('confidence', '?')} | Résumé: {result_t3.get('summary', 'N/A')}")
            return (result_t3, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)

        else:
            self.logger.info("   ✋ Fin de l'analyse (Tier 3 non déclenché).")
            result_t2["model_used"] = " -> ".join(model_chain)
            return (result_t2, gatekeeper_brand, gatekeeper_classification, gatekeeper_status, qwen_observation)
