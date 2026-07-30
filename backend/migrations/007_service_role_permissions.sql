-- Grant table-level permissions to the service_role.
-- Supabase's service_role key does NOT auto-acquire table privileges
-- when tables are created via raw SQL. Without these grants every
-- backend DB operation (all service-role queries) fails with 42501.

GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;
