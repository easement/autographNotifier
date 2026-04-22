-- Migration: add archived column to listings
-- Run this once against your Supabase database if the table already exists.

ALTER TABLE public.listings
    ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS listings_archived_idx
    ON public.listings (archived)
    WHERE archived = FALSE;
