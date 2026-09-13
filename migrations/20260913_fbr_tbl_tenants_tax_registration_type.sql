-- CHECKPOINT 8G-B — TAX REGISTRATION TYPE COLUMN
-- FBR-owned schema change only. No omtbl_* / ws_tbl* / Supabase internal changes.
-- Safe to run on fresh DB or existing DB where column already exists.

BEGIN;

-- Add column if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'fbr_tbl_tenants'
          AND column_name  = 'tax_registration_type'
    ) THEN
        ALTER TABLE public.fbr_tbl_tenants
            ADD COLUMN tax_registration_type text NULL;
    END IF;
END $$;

-- Add CHECK constraint if missing
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname     = 'chk_fbr_tbl_tenants_tax_registration_type'
          AND conrelid    = 'public.fbr_tbl_tenants'::regclass
          AND contype     = 'c'
    ) THEN
        ALTER TABLE public.fbr_tbl_tenants
            ADD CONSTRAINT chk_fbr_tbl_tenants_tax_registration_type
            CHECK (tax_registration_type IN ('sales_tax_registered', 'not_sales_tax_registered'));
    END IF;
END $$;

COMMIT;
