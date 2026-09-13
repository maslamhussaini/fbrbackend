-- CHECKPOINT 7D.2 — CLIENT OPERATION IDEMPOTENCY TABLE
-- FBR-owned infrastructure table. No omtbl_* / ws_tbl* changes.

BEGIN;

CREATE TABLE IF NOT EXISTS public.fbr_tbl_sync_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    operation_id UUID NOT NULL,
    entity_type TEXT NOT NULL,
    action TEXT NOT NULL,
    record_id TEXT,
    status TEXT NOT NULL DEFAULT 'processing',
    response_status INTEGER,
    response_body JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    last_error TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_operations_tenant_operation
    ON public.fbr_tbl_sync_operations (tenant_id, operation_id);

CREATE INDEX IF NOT EXISTS idx_sync_operations_tenant_created
    ON public.fbr_tbl_sync_operations (tenant_id, created_at);

-- Safe FK reference to existing FBR tenant table only.
-- Do not reference protected tables.
-- Using the same UUID convention as existing fbr_tbl_tenants.id.
ALTER TABLE public.fbr_tbl_sync_operations
    ADD CONSTRAINT fk_sync_operations_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES public.fbr_tbl_tenants(id)
    ON DELETE CASCADE;

COMMIT;
