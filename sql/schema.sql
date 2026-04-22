-- Autograph Notifier — Supabase schema
-- Run this in the Supabase SQL editor to create the listings table.

CREATE TABLE IF NOT EXISTS public.listings (
    hash                TEXT PRIMARY KEY,   -- SHA-256 fingerprint of shop|url
    shop                TEXT,               -- 'Park Ave CDs' | 'SG Record Shop' | '3hive' | 'Banquet Records'
    artist              TEXT,
    title               TEXT,
    format              TEXT,               -- 'LP' | 'CD' | '7"' | '10"' | 'cassette' | 'unknown'
    signed_by           TEXT,               -- 'band' | 'solo' | 'unknown'
    signature_location  TEXT,               -- 'cover' | 'insert' | 'booklet' | 'sleeve' | 'label' | 'unknown'
    price               TEXT,
    url                 TEXT,
    image_url           TEXT,
    description         TEXT,
    first_seen          TIMESTAMPTZ,        -- When the listing was first scraped
    last_seen           TIMESTAMPTZ,        -- Updated on every subsequent scrape
    archived            BOOLEAN NOT NULL DEFAULT FALSE  -- TRUE when item is no longer found in shop
);

-- Index for fast date-grouped queries
CREATE INDEX IF NOT EXISTS listings_first_seen_idx ON public.listings (first_seen DESC);

-- Index for filtering active (non-archived) listings
CREATE INDEX IF NOT EXISTS listings_archived_idx ON public.listings (archived) WHERE archived = FALSE;
