-- CHECKPOINT 5 — CONTROLLED FBR DATABASE PREFIX MIGRATION
-- MIGRATION SQL ONLY
-- NO OTHER SCHEMA OR DATA MODIFICATION

BEGIN;

ALTER TABLE public.tenants RENAME TO fbr_tbl_tenants;
ALTER TABLE public.user_profiles RENAME TO fbr_tbl_user_profiles;
ALTER TABLE public.customers RENAME TO fbr_tbl_customers;
ALTER TABLE public.products RENAME TO fbr_tbl_products;
ALTER TABLE public.invoices RENAME TO fbr_tbl_invoices;
ALTER TABLE public.invoice_items RENAME TO fbr_tbl_invoice_items;
ALTER TABLE public.upload_batches RENAME TO fbr_tbl_upload_batches;
ALTER TABLE public.invoice_queue RENAME TO fbr_tbl_invoice_queue;
ALTER TABLE public.scheduler_settings RENAME TO fbr_tbl_scheduler_settings;
ALTER TABLE public.hs_codes RENAME TO fbr_tbl_hs_codes;
ALTER TABLE public.uom_master RENAME TO fbr_tbl_uom_master;
ALTER TABLE public.provinces RENAME TO fbr_tbl_provinces;
ALTER TABLE public.cities RENAME TO fbr_tbl_cities;
ALTER TABLE public.tax_schedules RENAME TO fbr_tbl_tax_schedules;
ALTER TABLE public.sale_type_codes RENAME TO fbr_tbl_sale_type_codes;
ALTER TABLE public.scenario_types RENAME TO fbr_tbl_scenario_types;
ALTER TABLE public.uom_codes RENAME TO fbr_tbl_uom_codes;
ALTER TABLE public.fbr_api_logs RENAME TO fbr_tbl_api_logs;

COMMIT;
