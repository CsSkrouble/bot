SET TIME ZONE UTC;

ALTER TABLE IF EXISTS emote RENAME TO emotes;

CREATE TABLE IF NOT EXISTS emotes(
	name VARCHAR(32) NOT NULL,
	id BIGINT PRIMARY KEY,
	author BIGINT NOT NULL,
	animated BOOLEAN DEFAULT FALSE,
	description VARCHAR(280),
	created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
	modified TIMESTAMP WITH TIME ZONE,
	preserve BOOLEAN DEFAULT FALSE,
	guild BIGINT NOT NULL);

CREATE UNIQUE INDEX IF NOT EXISTS emotes_lower_idx ON emotes (LOWER(name));
CREATE INDEX IF NOT EXISTS emotes_name_trgm_idx ON emotes USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS emotes_author_idx ON emotes (author);

-- all this nonsense for "ADD PRIMARY KEY IF NOT EXISTS" lol
-- we're adding a PK so that JOINS will work btw
DO $$ BEGIN
	IF NOT EXISTS (
		SELECT constraint_name
		FROM information_schema.table_constraints
		WHERE table_name = 'emotes'
		      AND constraint_type = 'PRIMARY KEY'
	) THEN
		ALTER TABLE emotes
			ADD PRIMARY KEY (id); END IF; END; $$;

CREATE TABLE IF NOT EXISTS _guilds(
	id BIGINT NOT NULL UNIQUE PRIMARY KEY);

ALTER TABLE emotes
	DROP CONSTRAINT IF EXISTS emotes_guild_fkey,
	ADD CONSTRAINT emotes_guild_fkey FOREIGN KEY (guild)
		REFERENCES _guilds (id) ON DELETE CASCADE;

CREATE OR REPLACE VIEW guilds AS
	-- thanks to ysch on freenode/#postgresql for helping me with this query
	SELECT g.id,
	COUNT(e.guild) AS usage,
	COUNT(e.guild) FILTER (WHERE NOT e.animated) AS static_usage,
	COUNT(e.guild) FILTER (WHERE e.animated) AS animated_usage
	FROM _guilds AS g
	LEFT JOIN
		emotes AS e
		ON e.guild = g.id
	GROUP BY g.id;

-- https://stackoverflow.com/a/26284695/1378440
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
	IF row(NEW.*) IS DISTINCT FROM row(OLD.*) THEN
		NEW.modified = CURRENT_TIMESTAMP;
		RETURN NEW;
	ELSE
		RETURN OLD; END IF; END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_emote_modtime ON emotes;

CREATE TRIGGER update_emote_modtime
BEFORE UPDATE ON emotes
FOR EACH ROW EXECUTE PROCEDURE update_modified_column();

DROP TABLE IF EXISTS blacklists;

CREATE TABLE IF NOT EXISTS user_opt(
	id BIGINT NOT NULL UNIQUE,
	state BOOLEAN,
	blacklist_reason VARCHAR(500));

CREATE TABLE IF NOT EXISTS guild_opt(
	id BIGINT NOT NULL UNIQUE,
	state BOOLEAN NOT NULL);

CREATE TABLE IF NOT EXISTS emote_usage_history(
	id BIGINT,
	time TIMESTAMP WITH TIME ZONE DEFAULT (CURRENT_TIMESTAMP));

CREATE INDEX IF NOT EXISTS emote_usage_history_id_idx ON emote_usage_history (id);

-- https://stackoverflow.com/a/25499662
ALTER TABLE emote_usage_history
	DROP CONSTRAINT IF EXISTS emote_usage_history_id_fkey,
	ADD CONSTRAINT emote_usage_history_id_fkey FOREIGN KEY (id)
		REFERENCES emotes (id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS emote_usage_history_time_idx ON emote_usage_history (time);

ALTER TABLE IF EXISTS api_token RENAME TO api_tokens;

CREATE TABLE IF NOT EXISTS api_tokens(
	id BIGINT PRIMARY KEY NOT NULL UNIQUE,
	secret BYTEA NOT NULL);

CREATE INDEX IF NOT EXISTS api_token_secret_idx ON api_tokens (secret);
CREATE INDEX IF NOT EXISTS api_token_id_secret_idx ON api_tokens (id, secret);

CREATE TABLE IF NOT EXISTS locales(
	guild BIGINT,
	channel BIGINT,
	"user" BIGINT UNIQUE,
	locale VARCHAR(32) NOT NULL);

CREATE INDEX IF NOT EXISTS locales_guild_idx ON locales (guild);
CREATE INDEX IF NOT EXISTS locales_guild_idx ON locales (channel);
CREATE INDEX IF NOT EXISTS locales_guild_idx ON locales ("user");

CREATE UNIQUE INDEX IF NOT EXISTS locales_guild_channel_unique_index ON locales (guild, channel);

ALTER TABLE locales DROP CONSTRAINT IF EXISTS locales_check;
ALTER TABLE locales ADD CONSTRAINT locales_check CHECK (
	   guild IS NOT NULL AND channel IS NULL AND "user" IS NULL
	OR guild IS NOT NULL AND channel IS NOT NULL
	OR channel IS NOT NULL
	OR "user" IS NOT NULL);

-- old stuff --

DROP INDEX IF EXISTS emojis_id_key;
DROP INDEX IF EXISTS emojis_lower_idx;
DROP INDEX IF EXISTS emojis_author_idx;

DROP INDEX IF EXISTS emote_id_key;
DROP INDEX IF EXISTS emote_lower_idx;
DROP INDEX IF EXISTS emote_author_idx;

DROP TRIGGER IF EXISTS update_emoji_modtime ON emote;

DROP FUNCTION IF EXISTS str_contains;
