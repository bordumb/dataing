-- Require a webhook signing secret on every integration
--
-- Webhook signature verification fails closed: an integration without a
-- signing secret rejects every webhook. The only creation path
-- (POST /integrations) always generates a secret, so enforce it in the schema.
--
-- Idempotent: safe to re-run.

-- Rows created before this migration without a secret get a random one that
-- nobody holds, so they keep rejecting webhooks until an admin regenerates
-- the secret. The backfill also lets SET NOT NULL succeed.
UPDATE integrations
SET signing_secret = replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', ''),
    updated_at = NOW()
WHERE signing_secret IS NULL;

ALTER TABLE integrations ALTER COLUMN signing_secret SET NOT NULL;
