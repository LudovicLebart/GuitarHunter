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

CREATE TABLE IF NOT EXISTS guitar_deals (
    id                          TEXT PRIMARY KEY,
    user_id                     TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
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
    is_favorite                 BOOLEAN NOT NULL DEFAULT false,
    is_purchased                BOOLEAN NOT NULL DEFAULT false,
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

-- Colonnes indexées natives : remplacent le sharding manuel de `deals_index` (20 chunks
-- Firestore) — un index SQL fait ce travail sans bricolage applicatif.
CREATE INDEX IF NOT EXISTS idx_guitar_deals_user_id    ON guitar_deals(user_id);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_status      ON guitar_deals(user_id, status);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_verdict     ON guitar_deals(user_id, verdict);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_timestamp   ON guitar_deals(user_id, "timestamp" DESC);
CREATE INDEX IF NOT EXISTS idx_guitar_deals_favorite    ON guitar_deals(user_id, is_favorite) WHERE is_favorite;
CREATE INDEX IF NOT EXISTS idx_guitar_deals_classification ON guitar_deals(user_id, classification);

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
CREATE TABLE IF NOT EXISTS restoration_plan_items (
    id           BIGSERIAL PRIMARY KEY,
    deal_id      TEXT NOT NULL REFERENCES guitar_deals(id) ON DELETE CASCADE,
    label        TEXT,
    category     TEXT,
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
CREATE OR REPLACE FUNCTION notify_deal_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('deal_changes', json_build_object('user_id', NEW.user_id, 'id', NEW.id)::text);
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

CREATE TABLE IF NOT EXISTS cities (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    latitude    DOUBLE PRECISION,
    longitude   DOUBLE PRECISION,
    needs_review BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_city_prefs (
    user_id     TEXT NOT NULL REFERENCES users(uid) ON DELETE CASCADE,
    city_id     TEXT NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
    active      BOOLEAN NOT NULL DEFAULT true,
    PRIMARY KEY (user_id, city_id)
);

-- Table publique (partage d'annonce) : exposée sans auth côté API, équivalent
-- `allow read: if true` des règles Firestore actuelles.
CREATE TABLE IF NOT EXISTS shared_deals (
    id          TEXT PRIMARY KEY,
    deal_id     TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    snapshot    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
