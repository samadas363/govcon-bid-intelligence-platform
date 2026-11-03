```sql
-- ============================================================
-- PROJECT: GovCon BD Intelligence & Automation Platform
-- FILE: verification_queries.sql
-- PURPOSE: Verify database tables, sample data, and relationships
-- DATABASE: govcon_bd
-- ============================================================


-- ============================================================
-- QUERY 1: List all project tables
-- Expected: 17 tables
-- ============================================================

SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;


-- ============================================================
-- QUERY 2: Count records in each project table
-- ============================================================

SELECT 'company_profiles' AS table_name, COUNT(*) AS total_records
FROM company_profiles

UNION ALL
SELECT 'company_naics', COUNT(*) FROM company_naics

UNION ALL
SELECT 'company_capabilities', COUNT(*) FROM company_capabilities

UNION ALL
SELECT 'certifications', COUNT(*) FROM certifications

UNION ALL
SELECT 'past_performance', COUNT(*) FROM past_performance

UNION ALL
SELECT 'opportunities', COUNT(*) FROM opportunities

UNION ALL
SELECT 'opportunity_scores', COUNT(*) FROM opportunity_scores

UNION ALL
SELECT 'prime_contractors', COUNT(*) FROM prime_contractors

UNION ALL
SELECT 'contacts', COUNT(*) FROM contacts

UNION ALL
SELECT 'interactions', COUNT(*) FROM interactions

UNION ALL
SELECT 'teaming_relationships', COUNT(*) FROM teaming_relationships

UNION ALL
SELECT 'proposals', COUNT(*) FROM proposals

UNION ALL
SELECT 'proposal_requirements', COUNT(*) FROM proposal_requirements

UNION ALL
SELECT 'follow_up_tasks', COUNT(*) FROM follow_up_tasks

UNION ALL
SELECT 'awards', COUNT(*) FROM awards

UNION ALL
SELECT 'debriefs', COUNT(*) FROM debriefs

UNION ALL
SELECT 'automation_logs', COUNT(*) FROM automation_logs

ORDER BY table_name;


-- ============================================================
-- QUERY 3: View company profile
-- ============================================================

SELECT *
FROM company_profiles
ORDER BY created_at DESC;


-- ============================================================
-- QUERY 4: View company NAICS codes
-- ============================================================

SELECT *
FROM company_naics
ORDER BY naics_code;


-- ============================================================
-- QUERY 5: View company capabilities
-- ============================================================

SELECT *
FROM company_capabilities
ORDER BY capability_name;


-- ============================================================
-- QUERY 6: View opportunities
-- ============================================================

SELECT *
FROM opportunities
ORDER BY response_deadline NULLS LAST;


-- ============================================================
-- QUERY 7: View opportunity fit scores
-- ============================================================

SELECT *
FROM opportunity_scores
ORDER BY total_score DESC NULLS LAST;


-- ============================================================
-- QUERY 8: Opportunity pipeline with fit scores
-- Shows the opportunity details and score when available.
-- ============================================================

SELECT
    o.id AS opportunity_id,
    o.external_id,
    o.title,
    o.agency,
    o.naics_code,
    o.response_deadline,
    o.source,
    o.is_sample_data,
    s.total_score,
    s.recommendation
FROM opportunities AS o
LEFT JOIN opportunity_scores AS s
    ON s.opportunity_id = o.id
ORDER BY s.total_score DESC NULLS LAST;


-- ============================================================
-- QUERY 9: View prime contractors
-- ============================================================

SELECT *
FROM prime_contractors
ORDER BY company_name;


-- ============================================================
-- QUERY 10: View contacts and their associated primes
-- ============================================================

SELECT
    c.id AS contact_id,
    c.first_name,
    c.last_name,
    c.job_title,
    c.email,
    p.company_name AS prime_contractor
FROM contacts AS c
LEFT JOIN prime_contractors AS p
    ON p.id = c.prime_id
ORDER BY p.company_name, c.last_name;


-- ============================================================
-- QUERY 11: View follow-up tasks
-- ============================================================

SELECT *
FROM follow_up_tasks
ORDER BY due_date NULLS LAST;


-- ============================================================
-- QUERY 12: Check sample versus non-sample opportunities
-- ============================================================

SELECT
    is_sample_data,
    COUNT(*) AS opportunity_count
FROM opportunities
GROUP BY is_sample_data
ORDER BY is_sample_data DESC;


-- ============================================================
-- QUERY 13: Check for opportunities without fit scores
-- Expected: 0 rows if every opportunity has been scored.
-- ============================================================

SELECT
    o.id,
    o.external_id,
    o.title
FROM opportunities AS o
LEFT JOIN opportunity_scores AS s
    ON s.opportunity_id = o.id
WHERE s.opportunity_id IS NULL;


-- ============================================================
-- QUERY 14: Check for duplicate external opportunity IDs
-- Expected: 0 rows if the IDs are unique.
-- ============================================================

SELECT
    external_id,
    COUNT(*) AS duplicate_count
FROM opportunities
WHERE external_id IS NOT NULL
GROUP BY external_id
HAVING COUNT(*) > 1;


-- ============================================================
-- QUERY 15: Check database connection and version
-- ============================================================

SELECT
    current_database() AS database_name,
    current_user AS database_user,
    version() AS postgresql_version;


-- ============================================================
-- END OF VERIFICATION QUERIES
-- ============================================================
```