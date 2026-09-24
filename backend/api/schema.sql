-- Schéma Postgres — remplace les collections Firestore (voir
-- docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §2 pour le mapping complet).
--
-- Toutes les instructions sont idempotentes (CREATE TABLE/INDEX IF NOT EXISTS) pour pouvoir
-- être rejouées sans risque au démarrage du service API (backend/api/db.py::init_db()).
--
-- Isolation multi-tenant : chaque table métier porte un `user_id` (uid Firebase) et
-- l'application filtre systématiquement dessus (remplace les Firestore Security Rules,
-- voir FIRESTORE_MIGRATION_PLAN.md §1 "Auth inchangée").

CREATE TABLE IF NOT EXISTS users (
    uid              TEXT PRIMARY KEY,
    bot_status       TEXT NOT NULL DEFAULT 'idle',
    config           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Temps réel (remplace `onBotConfigUpdate`, Phase A.2) : même principe que `notify_deal_change`
-- ci-dessous — un seul canal partagé, filtré par `user_id` côté serveur WS, pas un canal par uid.
CREATE OR REPLACE FUNCTION notify_user_config_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('user_config_changes', json_build_object('user_id', NEW.uid)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_notify ON users;
CREATE TRIGGER users_notify
    AFTER INSERT OR UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION notify_user_config_change();

-- 2026-09-19 : `guitar_deals` est un CATALOGUE PARTAGÉ, pas une table par utilisateur — une
-- annonce réelle (id Facebook/Kijiji) n'a qu'une seule ligne, scrapée et analysée UNE FOIS,
-- quel que soit le nombre d'utilisateurs dont la recherche la recoupe (décision explicite de
-- l'utilisateur, suite au bug cross-tenant trouvé le même jour : `user_id` en clé unique était
-- une erreur d'architecture, pas juste un bug d'upsert — voir JOURNAL.md). "Qui voit quoi" et
-- "préférences personnelles" vivent dans `user_deal_matches`/`user_deal_state` ci-dessous ;
-- "qui a acheté" reste sur cette table (fait global : une guitare vendue l'est pour tout le
-- monde), voir `purchased_by_user_id`.
CREATE TABLE IF NOT EXISTS guitar_deals (
    id                          TEXT PRIMARY KEY,
    title                       TEXT,
    price                       NUMERIC,
    original_price              NUMERIC,
    price_drop_amount           NUMERIC,
    status                      TEXT NOT NULL DEFAULT 'analyzed',
    verdict                     TEXT,
    classification              TEXT,
    classification_rejected     TEXT,
    brand                       TEXT,
    model_name                  TEXT,
    production_year             TEXT,
    country_of_origin           TEXT,
    color                       TEXT,
    finish_application          TEXT,
    finish_texture              TEXT,
    deal_score                  SMALLINT,
    authenticity_score          SMALLINT,
    condition_score             SMALLINT,
    liquidity_score             SMALLINT,
    restoration_interest_score  SMALLINT,
    model_used                  TEXT,
    tier3_trigger               TEXT,
    initial_verdict             TEXT,
    initial_model_used          TEXT,
    is_purchased                BOOLEAN NOT NULL DEFAULT false,
    purchased_by_user_id        TEXT REFERENCES users(uid) ON DELETE SET NULL,
    manual_classification       TEXT,
    manual_analysis_overrides   JSONB,
    link                        TEXT,
    location                    TEXT,
    latitude                    DOUBLE PRECISION,
    longitude                   DOUBLE PRECISION,
    published_at_raw            TEXT,
    image_urls                  JSONB,
    storage_image_urls          JSONB,
    storage_image_gs_uris       JSONB,
    ai_analysis_raw             JSONB,      -- reasoning + tout champ non promu en colonne
    sold_at                     TIMESTAMPTZ,
    "timestamp"                 TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- `user_deal_matches` : remplace le rôle que jouait `user_id` sur `guitar_deals` pour la
-- VISIBILITÉ — quand le scan d'un utilisateur retrouve une annonce déjà analysée globalement
-- (même id), on n'analyse rien de plus, on enregistre juste que ce scan l'a "matchée" pour lui,
-- pour qu'elle apparaisse dans son fil. Pas de colonnes de préférence ici (voir
-- `user_deal_state` pour favori/rejet) : une seule ligne veut juste dire "visible pour cet
-- utilisateur", jamais mise à jour ensuite.
CREATE TABLE IF NOT EXISTS user_deal_matches (
    user_id     TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    deal_id     TEXT NOT NULL REFERENCES guitar_deals(id) ON DELETE CASCADE,
    matched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, deal_id)
);

CREATE INDEX IF NOT EXISTS idx_user_deal_matches_user ON user_deal_matches(user_id, matched_at DESC);

-- `user_deal_state` : préférences PERSONNELLES sur une annonce partagée — favori et rejet manuel
-- ("pas intéressé", décidé PAR UTILISATEUR : un rejet par A ne doit pas cacher l'annonce pour B,
-- contrairement au rejet AUTOMATIQUE par verdict IA qui reste sur `guitar_deals.status`, un fait
-- sur l'annonce elle-même). Absence de ligne == ni favori, ni rejeté (mêmes valeurs par défaut
-- que les anciennes colonnes `guitar_deals.is_favorite`/manuellement rejeté).
CREATE TABLE IF NOT EXISTS user_deal_state (
    user_id      TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    deal_id      TEXT NOT NULL REFERENCES guitar_deals(id) ON DELETE CASCADE,
    is_favorite  BOOLEAN NOT NULL DEFAULT false,
    is_rejected  BOOLEAN NOT NULL DEFAULT false,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, deal_id)
);

CREATE INDEX IF NOT EXISTS idx_user_deal_state_favorite ON user_deal_state(user_id) WHERE is_favorite;
CREATE INDEX IF NOT EXISTS idx_user_deal_state_rejected ON user_deal_state(user_id) WHERE is_rejected;

-- Correctif 2026-09-20 (revue de code) : le favori/rejet manuel ne touche plus `guitar_deals`
-- (colonnes déplacées ici), donc ne déclenchait plus AUCUNE notification WS — le frontend ne
-- voyait plus la bascule en temps réel sur un second onglet/appareil. Réutilise le même canal
-- `deal_changes` que `notify_deal_change` (même payload `{"id": deal_id}`, le consommateur WS
-- ne distingue pas la table d'origine, seulement la visibilité du deal_id pour l'utilisateur
-- connecté — voir main.py::ws_deals::_push_if_visible).
CREATE OR REPLACE FUNCTION notify_user_deal_state_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('deal_changes', json_build_object('id', COALESCE(NEW.deal_id, OLD.deal_id))::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_deal_state_notify ON user_deal_state;
CREATE TRIGGER user_deal_state_notify
    AFTER INSERT OR UPDATE ON user_deal_state
    FOR EACH ROW EXECUTE FUNCTION notify_user_deal_state_change();

-- `purchased_by_user_id` : absente d'une base déjà initialisée avant le 2026-09-19 (comme
-- toute colonne ajoutée après la création initiale, voir l'avertissement plus bas) — ajoutée ici
-- en ALTER explicite avant les index qui la référencent.
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS purchased_by_user_id TEXT REFERENCES users(uid) ON DELETE SET NULL;

-- Colonnes indexées natives : remplacent le sharding manuel de `deals_index` (20 chunks
-- Firestore) — un index SQL fait ce travail sans bricolage applicatif. Plus de `user_id` ici
-- (catalogue partagé, voir commentaire au-dessus de `CREATE TABLE guitar_deals`) — les index
-- filtrés PAR utilisateur vivent désormais sur `user_deal_matches`/`user_deal_state`.
--
-- ATTENTION piège réel (trouvé en revue de code, 2026-09-20) : ces 4 index reprennent le MÊME
-- NOM que les anciens index à 2 colonnes `(user_id, ...)` qu'ils remplacent. Sur une base déjà
-- initialisée, à ce stade du script `user_id` existe ENCORE (le bloc de backfill/DROP COLUMN
-- plus bas n'a pas encore tourné) — le `CREATE INDEX IF NOT EXISTS` ci-dessous serait alors un
-- no-op silencieux (nom déjà pris par l'ancien index 2-colonnes), et le `DROP COLUMN user_id`
-- plus bas dropperait ensuite cet ancien index par cascade SANS que le nouveau (1 colonne)
-- n'ait jamais été créé — la table se retrouverait sans AUCUN index sur ces 4 colonnes jusqu'au
-- prochain redémarrage/ré-exécution de ce fichier. `DROP INDEX IF EXISTS` explicite ci-dessous
-- avant chaque `CREATE INDEX` pour garantir un résultat correct dès la PREMIÈRE exécution,
-- quel que soit l'état de la base (idempotent : sans effet sur une base déjà à jour).
DROP INDEX IF EXISTS idx_guitar_deals_status;
DROP INDEX IF EXISTS idx_guitar_deals_verdict;
DROP INDEX IF EXISTS idx_guitar_deals_timestamp;
DROP INDEX IF EXISTS idx_guitar_deals_classification;
CREATE INDEX IF NOT EXISTS idx_guitar_deals_status      ON guitar_deals(status);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_verdict     ON guitar_deals(verdict);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_timestamp   ON guitar_deals("timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_classification ON guitar_deals(classification);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_purchased_by ON guitar_deals(purchased_by_user_id) WHERE purchased_by_user_id IS NOT NULL;

-- Migration d'une base déjà initialisée avec l'ANCIEN schéma (`user_id` par ligne, un
-- "propriétaire" unique par annonce) : `CREATE TABLE IF NOT EXISTS` ci-dessus est un no-op sur
-- une table déjà créée, donc `user_id` (et l'ancien `is_favorite`) y sont encore présents tant
-- que ce bloc n'a pas tourné. Backfill AVANT toute suppression de colonne — perdre `user_id` en
-- premier perdrait aussi l'information "qui voyait déjà cette annonce" / "qui l'avait mise en
-- favori" sans espoir de la reconstruire.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'guitar_deals' AND column_name = 'user_id'
    ) THEN
        INSERT INTO user_deal_matches (user_id, deal_id)
        SELECT user_id, id FROM guitar_deals
        ON CONFLICT (user_id, deal_id) DO NOTHING;

        INSERT INTO user_deal_state (user_id, deal_id, is_favorite)
        SELECT user_id, id, is_favorite FROM guitar_deals WHERE is_favorite
        ON CONFLICT (user_id, deal_id) DO UPDATE SET is_favorite = true;

        UPDATE guitar_deals SET purchased_by_user_id = user_id
        WHERE is_purchased AND purchased_by_user_id IS NULL;

        DROP INDEX IF EXISTS idx_guitar_deals_user_id;
        DROP INDEX IF EXISTS idx_guitar_deals_favorite;
        ALTER TABLE guitar_deals DROP COLUMN user_id;
        ALTER TABLE guitar_deals DROP COLUMN IF EXISTS is_favorite;
    END IF;
END $$;

-- `purchase_price`/`purchased_at` manquaient du tout premier jet de ce schéma alors que
-- deals_repo.py::toggle_purchased les référence depuis la tranche 2 — bug latent jamais
-- détecté faute de test de correction fonctionnelle sur cet endpoint (trouvé en écrivant un
-- tel test lors d'une revue de code). Ajoutées ici en ALTER TABLE (voir l'avertissement
-- juste en dessous : `guitar_deals` est déjà créée sur toute base ayant déjà joué ce fichier).
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS purchase_price NUMERIC;
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS purchased_at   TIMESTAMPTZ;

-- `description` : présente dans `listing_data` du scraper (parser.py, jusqu'à 3000 caractères)
-- et spread dans le document Firestore par `create_new_deal`/`update_deal_data_and_analysis`,
-- mais jamais promue en colonne ici — trouvé en traçant le vrai besoin de lecture du bot
-- (`analyze_single_deal`/`bot.py`) pour la Phase A.1 (bascule bot -> Postgres, voir
-- docs/management/plans/FIRESTORE_MIGRATION_PLAN.md §5.3), pas par l'export ponctuel (qui
-- l'aurait silencieusement rangée dans `ai_analysis_raw['_unmapped']` sans le signaler comme
-- un manque — seule une relecture attentive du CODE CONSOMMATEUR, pas des données migrées,
-- pouvait le révéler).
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS description TEXT;

-- `sold_notes` : équivalent du champ Firestore `soldNotes` (tableau `[{info, timestamp}, ...]`,
-- alimenté par `mark_deal_as_sold(reason=...)`) — trouvé manquant en même temps que
-- `description`, en traçant les besoins réels du bot pour la Phase A.1. L'export ponctuel le
-- rangeait jusqu'ici dans `ai_analysis_raw['_unmapped']` (garde-fou générique) faute de colonne
-- dédiée ; devient un champ mappé normalement désormais.
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS sold_notes JSONB;

-- `published_at_ts` : timestamp de publication de l'annonce (epoch secondes), parsé une fois au
-- scraping depuis `published_at_raw` (voir `backend/scraping/parser.py::parse_french_date`) —
-- jamais promu en colonne sur le document Firestore complet, seulement injecté dans l'index en
-- chunks (`repository.py::_update_deal_index`, clé `pt`). Trouvé manquant en traçant les besoins
-- réels du FRONTEND (Phase A.2, tri "date de publication" et statistiques de délai de vente dans
-- StatsView.jsx/DealsExplorer.jsx) plutôt que ceux du bot — sans lui, ces deux fonctionnalités
-- retomberaient silencieusement sur 0 (pas un crash, mais un tri/calcul faux). BIGINT (epoch
-- secondes brut) plutôt que TIMESTAMPTZ : évite un aller-retour de conversion, la seule
-- consommation frontend attendue est une comparaison numérique directe.
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS published_at_ts BIGINT;

-- `gatekeeper_brand`/`gatekeeper_classification`/`gatekeeper_verdict` : rattrapage Chantier G
-- (routage par recherche active, `activeSearchFamilies`) — ajouté sur `dev` après le fork de
-- cette branche (2026-09-09), jamais porté ici jusqu'au 2026-09-19. Verdict/marque/classification
-- BRUTS du Portier (Tier 1), toujours attachés par `analyzer.py::_attach_gatekeeper_metadata`
-- quel que soit le sort de l'annonce ensuite (contrairement à `verdict`/`brand`/`classification`,
-- qui reflètent la DERNIÈRE étape ayant tourné) — nécessaires pour retrouver, sans rappeler le
-- Portier, la classification d'une annonce `NOT_PROMOTED` quand le filtre change
-- (`bot.py::reevaluate_not_promoted`).
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS gatekeeper_brand TEXT;
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS gatekeeper_classification TEXT;
ALTER TABLE guitar_deals ADD COLUMN IF NOT EXISTS gatekeeper_verdict TEXT;

-- ATTENTION migrations : `CREATE TABLE IF NOT EXISTS` ne modifie JAMAIS une table déjà
-- existante — toute colonne ajoutée après la création initiale d'une table DOIT passer par
-- un `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` séparé (comme ci-dessous), sinon elle
-- n'est silencieusement jamais appliquée sur une base déjà initialisée par une tranche
-- précédente (piège réel rencontré en écrivant la tranche 3 — chat).
CREATE TABLE IF NOT EXISTS deal_chat (
    id            BIGSERIAL PRIMARY KEY,
    deal_id       TEXT NOT NULL REFERENCES guitar_deals(id) ON DELETE CASCADE,
    role          TEXT NOT NULL,
    parts         JSONB NOT NULL DEFAULT '[]'::jsonb,
    display_text  TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS attached_image_part_indices JSONB;       -- tableau d'index dans `parts`
ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS restoration_proposals       JSONB;       -- tableau de propositions (statut inclus par item)
ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS added_to_gallery_urls       JSONB;       -- map {"<partIndex>": url}
ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS photo_recall                JSONB;
ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS is_error                    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE deal_chat ADD COLUMN IF NOT EXISTS requalification_proposal    JSONB;

CREATE INDEX IF NOT EXISTS idx_deal_chat_deal_id ON deal_chat(deal_id, created_at);

-- Temps réel du chat (remplace onDealChatUpdate) : canal séparé de deal_changes, filtré par
-- deal_id côté serveur WS (pas par user_id — la propriété du deal est vérifiée une fois à la
-- connexion, voir main.py::ws_deal_chat).
CREATE OR REPLACE FUNCTION notify_chat_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('chat_changes', json_build_object('deal_id', NEW.deal_id, 'id', NEW.id)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS deal_chat_notify ON deal_chat;
CREATE TRIGGER deal_chat_notify
    AFTER INSERT OR UPDATE ON deal_chat
    FOR EACH ROW EXECUTE FUNCTION notify_chat_change();

-- Colonnes cost_low/cost_high de la première version de ce schéma (avant lecture complète du
-- contrat réel dans firestoreService.js) jamais utilisées par aucun code — remplacées ici
-- avant toute tranche 4 par les vrais champs (estimated_cost/actual_cost/source/...), voir
-- addRestorationItem/updateRestorationItem. Retirées explicitement plutôt que laissées mortes.
-- `status` inclus dès le CREATE TABLE (nullable ici) : sur une base fraîche, un simple
-- ADD COLUMN IF NOT EXISTS status ... plus bas serait un no-op silencieux si la colonne
-- existe déjà (voir le piège documenté juste après), mais s'il ne l'était PAS déjà présente,
-- les ALTER COLUMN suivants échoueraient avec "column status does not exist" — la colonne
-- doit donc exister dès la création, quelle que soit l'histoire de la base cible.
CREATE TABLE IF NOT EXISTS restoration_plan_items (
    id           BIGSERIAL PRIMARY KEY,
    deal_id      TEXT NOT NULL REFERENCES guitar_deals(id) ON DELETE CASCADE,
    label        TEXT,
    category     TEXT,
    status       TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE restoration_plan_items DROP COLUMN IF EXISTS cost_low;
ALTER TABLE restoration_plan_items DROP COLUMN IF EXISTS cost_high;
-- `status` existait déjà (sans défaut) dans la toute première version de ce schéma : un simple
-- ADD COLUMN IF NOT EXISTS est alors un no-op qui n'applique JAMAIS le nouveau défaut/contrainte
-- (même piège que documenté plus haut, mais sur une colonne existante plutôt qu'absente) — d'où
-- les 3 lignes explicites ci-dessous plutôt qu'un simple ADD COLUMN.
ALTER TABLE restoration_plan_items ALTER COLUMN status SET DEFAULT 'pending';
UPDATE restoration_plan_items SET status = 'pending' WHERE status IS NULL;
ALTER TABLE restoration_plan_items ALTER COLUMN status SET NOT NULL;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS estimated_cost          NUMERIC;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS actual_cost             NUMERIC;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS notes                   TEXT;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS source                  TEXT NOT NULL DEFAULT 'user';   -- 'user' | 'ai' (proposition Gemini appliquée)
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS proposed_by_message_id  BIGINT REFERENCES deal_chat(id) ON DELETE SET NULL;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS item_order              INTEGER;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS photo_urls              JSONB;
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS updated_at              TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE restoration_plan_items ADD COLUMN IF NOT EXISTS completed_at            TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_restoration_plan_deal_id ON restoration_plan_items(deal_id, item_order);

-- Temps réel (remplace onRestorationPlanUpdate) : canal séparé, filtré par deal_id comme
-- chat_changes. Couvre aussi DELETE (contrairement à deal_changes/chat_changes, qui n'en ont
-- pas besoin dans leurs flux actuels) car la suppression d'étape est une action réelle exposée
-- ici (deleteRestorationItem) — un client resterait sinon en désaccord avec la base jusqu'au
-- prochain reload.
CREATE OR REPLACE FUNCTION notify_restoration_plan_change() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('restoration_plan_changes', json_build_object('deal_id', OLD.deal_id, 'id', OLD.id, 'deleted', true)::text);
        RETURN OLD;
    END IF;
    PERFORM pg_notify('restoration_plan_changes', json_build_object('deal_id', NEW.deal_id, 'id', NEW.id)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS restoration_plan_items_notify ON restoration_plan_items;
CREATE TRIGGER restoration_plan_items_notify
    AFTER INSERT OR UPDATE OR DELETE ON restoration_plan_items
    FOR EACH ROW EXECUTE FUNCTION notify_restoration_plan_change();

-- Temps réel (remplace `onDealsIndexUpdate`, voir FIRESTORE_MIGRATION_PLAN.md §1) : un
-- trigger au niveau base notifie sur TOUTE écriture, quelle que soit son origine (bot en SQL
-- direct comme cette API) — plus fiable qu'un NOTIFY manuel à dupliquer dans chaque site
-- d'écriture applicatif. Canal unique `deal_changes` ; le filtrage par utilisateur se fait
-- côté serveur WS (backend/api/main.py), pas par un canal dédié par uid (échelle du projet
-- trop restreinte pour que ça vaille la complexité).
-- 2026-09-19 : ne pousse plus `user_id` (catalogue partagé, `guitar_deals` n'en a plus) — un
-- changement sur une annonce concerne potentiellement PLUSIEURS utilisateurs (tous ceux avec une
-- ligne dans `user_deal_matches` pour cet id) ; c'est à la couche WS (backend/api/main.py) de
-- déterminer qui est concerné en interrogeant cette table, pas au trigger de le décider.
CREATE OR REPLACE FUNCTION notify_deal_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('deal_changes', json_build_object('id', NEW.id)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS guitar_deals_notify ON guitar_deals;
CREATE TRIGGER guitar_deals_notify
    AFTER INSERT OR UPDATE ON guitar_deals
    FOR EACH ROW EXECUTE FUNCTION notify_deal_change();

-- Bus de commandes Frontend -> Backend (première tranche migrée, voir §3 du plan).
-- `status` : pending | completed | failed. Le bot lit directement cette table (accès SQL
-- direct, pas via l'API HTTP) ; seul le frontend passe par POST /commands.
CREATE TABLE IF NOT EXISTS commands (
    id            BIGSERIAL PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    payload       JSONB,
    status        TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_commands_pending ON commands(user_id, status, created_at) WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    message     TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'INFO',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_logs_user_created ON logs(user_id, created_at DESC);
-- Remplace la TTL policy Firestore (3 jours) : job cron/schedule côté API à écrire
-- (`DELETE FROM logs WHERE created_at < now() - interval '3 days'`), voir plan §2.

-- Catalogue partagé (remplace `artifacts/{APP_ID}/cities`, écrit par bot.py::add_city_auto()
-- avec un `.set(merge=True)` — hors périmètre ici : cette tranche ne construit que la surface
-- consommée par le frontend, le bot restant sur Firestore jusqu'à la bascule, voir §5.1).
CREATE TABLE IF NOT EXISTS cities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    needs_review BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE cities ADD COLUMN IF NOT EXISTS created_by TEXT;   -- uid, voir add_city_auto()

-- Préférences par utilisateur (remplace `users/{uid}/cities`, architecture actuelle). L'absence
-- de ligne pour un (user_id, city_id) donné == "non scannable" côté Firestore (`isScannable ??
-- false`, `onCitiesUpdate`) — d'où `active DEFAULT false` : une ligne créée UNIQUEMENT pour y
-- poser `kijiji_radius_km` (setCityKijijiRadius, `merge: true` côté Firestore, jamais
-- `isScannable` en même temps) ne doit jamais activer implicitement le scan de la ville.
CREATE TABLE IF NOT EXISTS user_city_prefs (
    user_id     TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    city_id     TEXT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    active      BOOLEAN NOT NULL DEFAULT false,
    PRIMARY KEY (user_id, city_id)
);

ALTER TABLE user_city_prefs ALTER COLUMN active SET DEFAULT false;   -- voir commentaire ci-dessus (corrige le défaut d'un tout premier jet, jamais utilisé jusqu'ici)
ALTER TABLE user_city_prefs ADD COLUMN IF NOT EXISTS kijiji_radius_km NUMERIC;

-- Temps réel (remplace les deux onSnapshot d'onCitiesUpdate) : contrairement à deal_changes/
-- chat_changes/restoration_plan_changes, on ne pousse ici qu'un signal léger (deal_id/city_id
-- concerné) plutôt que la ligne fusionnée — le calcul du merge catalogue+prefs vit côté requête
-- SQL (cities_repo.py::list_cities_for_user), pas dans le trigger ; le client réagit en
-- rafraîchissant l'entrée concernée. `user_city_prefs` est filtré par user_id (propre à chaque
-- utilisateur) ; `cities` (catalogue partagé) ne l'est pas, broadcast à tous les clients connectés.
CREATE OR REPLACE FUNCTION notify_city_pref_change() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_notify('city_prefs_changes', json_build_object('user_id', OLD.user_id, 'city_id', OLD.city_id)::text);
        RETURN OLD;
    END IF;
    PERFORM pg_notify('city_prefs_changes', json_build_object('user_id', NEW.user_id, 'city_id', NEW.city_id)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS user_city_prefs_notify ON user_city_prefs;
CREATE TRIGGER user_city_prefs_notify
    AFTER INSERT OR UPDATE OR DELETE ON user_city_prefs
    FOR EACH ROW EXECUTE FUNCTION notify_city_pref_change();

CREATE OR REPLACE FUNCTION notify_catalog_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('cities_catalog_changes', json_build_object('city_id', NEW.id)::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS cities_notify ON cities;
CREATE TRIGGER cities_notify
    AFTER INSERT OR UPDATE ON cities
    FOR EACH ROW EXECUTE FUNCTION notify_catalog_change();

-- Table publique (partage d'annonce) : exposée sans auth en LECTURE côté API, équivalent
-- `allow read: if true` / `allow write: if request.auth != null` des règles Firestore actuelles
-- (écriture par n'importe quel utilisateur authentifié, PAS réservée au propriétaire du deal —
-- vérifié dans firestore.rules, pas une supposition). `deal_id`/`user_id` de la première version
-- de ce schéma retirées : `createSharedDeal` (firestoreService.js) écrit `doc(db, 'shared_deals',
-- deal.id)` — l'id du document EST l'id du deal, jamais un id de partage séparé — et ne stocke
-- aucun `user_id` dans le document (write ouvert à tout utilisateur authentifié).
CREATE TABLE IF NOT EXISTS shared_deals (
    id          TEXT PRIMARY KEY,   -- = id du deal (guitar_deals.id), pas un id de partage séparé
    snapshot    JSONB NOT NULL,     -- payload exact écrit par createSharedDeal, opaque ici
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE shared_deals DROP COLUMN IF EXISTS deal_id;
ALTER TABLE shared_deals DROP COLUMN IF EXISTS user_id;

-- Chantier C-0 (tableau de bord de coût) : une ligne par appel LLM, backend ET chat, pour
-- connaître les tokens par modèle et par action. Écrite en best-effort (un échec d'insertion ne
-- bloque jamais une analyse ni un message de chat). `deal_id` sans FK : les scripts d'audit et de
-- rejeu touchent aussi des annonces supprimées depuis. `thoughts_tokens` = raisonnement, facturé
-- comme de la sortie mais compté à part par les fournisseurs. `cached_tokens` est INCLUS dans
-- `input_tokens` (même convention que Gemini `promptTokenCount` et OpenAI `prompt_tokens`).
CREATE TABLE IF NOT EXISTS llm_usage (
    id               BIGSERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source           TEXT NOT NULL,            -- 'backend' | 'chat'
    provider         TEXT NOT NULL,            -- 'gemini' | 'tokenrouter' | 'ollama' | ...
    model            TEXT NOT NULL,
    action           TEXT NOT NULL,            -- ex. 't1_gatekeeper', 't2_analyst', 'chat_turn'
    deal_id          TEXT,
    user_ref         TEXT,                     -- uid (chat) ou e-mail (bot), pour filtrer par utilisateur
    images           INTEGER NOT NULL DEFAULT 0,
    input_tokens     INTEGER NOT NULL DEFAULT 0,
    cached_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens    INTEGER NOT NULL DEFAULT 0,
    thoughts_tokens  INTEGER NOT NULL DEFAULT 0,
    latency_ms       INTEGER,
    ok               BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS llm_usage_created_idx ON llm_usage (created_at);
CREATE INDEX IF NOT EXISTS llm_usage_model_action_idx ON llm_usage (model, action, created_at);
