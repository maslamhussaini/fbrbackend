-- CHECKPOINT 5 — POST-MIGRATION VERIFICATION
-- READ-ONLY
-- NO DATABASE OBJECTS OR DATA ARE MODIFIED

-- ============================================================
-- 1. All 18 new fbr_tbl_* tables exist
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname IN (
        'fbr_tbl_tenants', 'fbr_tbl_user_profiles', 'fbr_tbl_customers',
        'fbr_tbl_products', 'fbr_tbl_invoices', 'fbr_tbl_invoice_items',
        'fbr_tbl_upload_batches', 'fbr_tbl_invoice_queue',
        'fbr_tbl_scheduler_settings', 'fbr_tbl_hs_codes', 'fbr_tbl_uom_master',
        'fbr_tbl_provinces', 'fbr_tbl_cities', 'fbr_tbl_tax_schedules',
        'fbr_tbl_sale_type_codes', 'fbr_tbl_scenario_types',
        'fbr_tbl_uom_codes', 'fbr_tbl_api_logs'
    )
ORDER BY table_name;

-- ============================================================
-- 2. None of the 18 old FBR table names remain
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname IN (
        'tenants', 'user_profiles', 'customers', 'products',
        'invoices', 'invoice_items', 'upload_batches', 'invoice_queue',
        'scheduler_settings', 'hs_codes', 'uom_master', 'provinces',
        'cities', 'tax_schedules', 'sale_type_codes', 'scenario_types',
        'uom_codes', 'fbr_api_logs'
    )
ORDER BY table_name;

-- ============================================================
-- 3. omtbl_* tables remain present and unchanged
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname LIKE 'omtbl\_%' ESCAPE '\'
ORDER BY table_name;

-- ============================================================
-- 4. ws_tbl* tables remain present and unchanged
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname LIKE 'ws\_tbl%' ESCAPE '\'
ORDER BY table_name;

-- ============================================================
-- 5. FK relationships still exist on renamed tables
-- ============================================================
SELECT 
    n.nspname AS source_schema,
    c.relname AS source_table,
    con.conname AS constraint_name,
    CASE con.contype
        WHEN 'p' THEN 'PRIMARY KEY'
        WHEN 'u' THEN 'UNIQUE'
        WHEN 'f' THEN 'FOREIGN KEY'
    END AS constraint_type,
    pg_catalog.pg_get_constraintdef(con.oid) AS constraint_definition
FROM pg_catalog.pg_constraint con
JOIN pg_catalog.pg_class c ON c.oid = con.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname IN (
        'fbr_tbl_tenants', 'fbr_tbl_user_profiles', 'fbr_tbl_customers',
        'fbr_tbl_products', 'fbr_tbl_invoices', 'fbr_tbl_invoice_items',
        'fbr_tbl_upload_batches', 'fbr_tbl_invoice_queue',
        'fbr_tbl_scheduler_settings', 'fbr_tbl_hs_codes', 'fbr_tbl_uom_master',
        'fbr_tbl_provinces', 'fbr_tbl_cities', 'fbr_tbl_tax_schedules',
        'fbr_tbl_sale_type_codes', 'fbr_tbl_scenario_types',
        'fbr_tbl_uom_codes', 'fbr_tbl_api_logs'
    )
ORDER BY source_table, constraint_type, constraint_name;

-- ============================================================
-- 6. RLS remains enabled on renamed tables
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relrowsecurity AS rls_enabled,
    c.relforcerowsecurity AS force_rls
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname IN (
        'fbr_tbl_tenants', 'fbr_tbl_user_profiles', 'fbr_tbl_customers',
        'fbr_tbl_products', 'fbr_tbl_invoices', 'fbr_tbl_invoice_items',
        'fbr_tbl_upload_batches', 'fbr_tbl_invoice_queue',
        'fbr_tbl_scheduler_settings', 'fbr_tbl_hs_codes', 'fbr_tbl_uom_master',
        'fbr_tbl_provinces', 'fbr_tbl_cities', 'fbr_tbl_tax_schedules',
        'fbr_tbl_sale_type_codes', 'fbr_tbl_scenario_types',
        'fbr_tbl_uom_codes', 'fbr_tbl_api_logs'
    )
ORDER BY table_name;

-- ============================================================
-- 7. Existing policies remain attached
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name,
    p.polname AS policy_name,
    p.polcmd AS command
FROM pg_catalog.pg_policy p
JOIN pg_catalog.pg_class c ON c.oid = p.polrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname IN (
        'fbr_tbl_tenants', 'fbr_tbl_user_profiles', 'fbr_tbl_customers',
        'fbr_tbl_products', 'fbr_tbl_invoices', 'fbr_tbl_invoice_items',
        'fbr_tbl_upload_batches', 'fbr_tbl_invoice_queue',
        'fbr_tbl_scheduler_settings', 'fbr_tbl_hs_codes', 'fbr_tbl_uom_master',
        'fbr_tbl_provinces', 'fbr_tbl_cities', 'fbr_tbl_tax_schedules',
        'fbr_tbl_sale_type_codes', 'fbr_tbl_scenario_types',
        'fbr_tbl_uom_codes', 'fbr_tbl_api_logs'
    )
ORDER BY table_name, policy_name;

-- ============================================================
-- 8. fbr_tbl_invoices still has expected triggers
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    p.proname AS trigger_function
FROM pg_catalog.pg_trigger t
JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc p ON p.oid = t.tgfoid
WHERE c.relkind = 'r'
    AND NOT t.tgisinternal
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND c.relname = 'fbr_tbl_invoices'
    AND t.tgname IN ('trg_close_on_submit', 'trg_invoice_number')
ORDER BY trigger_name;

-- ============================================================
-- 9. Trigger functions still exist
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    p.proname AS function_name
FROM pg_catalog.pg_proc p
JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND p.proname IN ('close_invoice_on_submit', 'set_invoice_number')
ORDER BY function_name;

-- ============================================================
-- 10. invoice_seq still exists
-- ============================================================
SELECT 
    n.nspname AS schema_name,
    s.relname AS sequence_name
FROM pg_catalog.pg_class s
JOIN pg_catalog.pg_namespace n ON n.oid = s.relnamespace
WHERE s.relkind = 'S'
    AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'supabase_migrations', 'auth', 'storage', 'realtime')
    AND n.nspname NOT LIKE 'pg_%'
    AND s.relname = 'invoice_seq'
ORDER BY sequence_name;

-- ============================================================
-- 11. Exact row counts after migration
-- ============================================================
SELECT 'fbr_tbl_tenants' AS table_name, COUNT(*) AS exact_rows FROM fbr_tbl_tenants
UNION ALL
SELECT 'fbr_tbl_user_profiles', COUNT(*) FROM fbr_tbl_user_profiles
UNION ALL
SELECT 'fbr_tbl_customers', COUNT(*) FROM fbr_tbl_customers
UNION ALL
SELECT 'fbr_tbl_products', COUNT(*) FROM fbr_tbl_products
UNION ALL
SELECT 'fbr_tbl_invoices', COUNT(*) FROM fbr_tbl_invoices
UNION ALL
SELECT 'fbr_tbl_invoice_items', COUNT(*) FROM fbr_tbl_invoice_items
UNION ALL
SELECT 'fbr_tbl_upload_batches', COUNT(*) FROM fbr_tbl_upload_batches
UNION ALL
SELECT 'fbr_tbl_invoice_queue', COUNT(*) FROM fbr_tbl_invoice_queue
UNION ALL
SELECT 'fbr_tbl_scheduler_settings', COUNT(*) FROM fbr_tbl_scheduler_settings
UNION ALL
SELECT 'fbr_tbl_hs_codes', COUNT(*) FROM fbr_tbl_hs_codes
UNION ALL
SELECT 'fbr_tbl_uom_master', COUNT(*) FROM fbr_tbl_uom_master
UNION ALL
SELECT 'fbr_tbl_provinces', COUNT(*) FROM fbr_tbl_provinces
UNION ALL
SELECT 'fbr_tbl_cities', COUNT(*) FROM fbr_tbl_cities
UNION ALL
SELECT 'fbr_tbl_tax_schedules', COUNT(*) FROM fbr_tbl_tax_schedules
UNION ALL
SELECT 'fbr_tbl_sale_type_codes', COUNT(*) FROM fbr_tbl_sale_type_codes
UNION ALL
SELECT 'fbr_tbl_scenario_types', COUNT(*) FROM fbr_tbl_scenario_types
UNION ALL
SELECT 'fbr_tbl_uom_codes', COUNT(*) FROM fbr_tbl_uom_codes
UNION ALL
SELECT 'fbr_tbl_api_logs', COUNT(*) FROM fbr_tbl_api_logs
ORDER BY table_name;

-- ============================================================
-- END OF CHECKPOINT 5 VERIFICATION
-- ============================================================
