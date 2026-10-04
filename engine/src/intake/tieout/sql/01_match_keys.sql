-- 01 Match keys: type the raw text, then tie each commission line to one policy in the book.
-- Money is DECIMAL(12,2) everywhere, never a float, so cents are never lost.

-- The tolerances and the rate table, typed once.
CREATE OR REPLACE VIEW tolerances AS
SELECT CAST(line_tolerance_usd AS DECIMAL(12, 2)) AS line_usd,
       CAST(line_tolerance_pct AS DECIMAL(6, 4)) AS line_pct,
       CAST(total_tolerance_pct AS DECIMAL(6, 4)) AS total_pct,
       CAST(new_business_months AS INTEGER) AS new_business_months
FROM settings;

-- The book: one row per policy_id. A duplicated policy (DUP-001, DUP-003) keeps its first
-- row, so a copy never doubles what the agency expects to be paid.
CREATE OR REPLACE VIEW book AS
SELECT * EXCLUDE (copy_number)
FROM (
    SELECT policy_id, client_id, carrier, carrier_member_id, line_of_business,
           TRY_CAST(effective_date AS DATE) AS effective_date,
           TRY_CAST(termination_date AS DATE) AS termination_date,
           upper(trim(status)) AS status,
           coalesce(nullif(trim(writing_agent_npn), ''), '(blank)') AS agent_npn,
           _source_file, _row_number, _raw_hash,
           row_number() OVER (PARTITION BY policy_id ORDER BY _row_number) AS copy_number
    FROM raw_policies
)
WHERE copy_number = 1;

-- Statement lines as the carrier sent them.
CREATE OR REPLACE VIEW statement_lines AS
SELECT carrier, statement_period,
       CAST(statement_period || '-01' AS DATE) AS period_start,
       CAST(line_no AS INTEGER) AS line_no,
       carrier_member_id, member_name,
       TRY_CAST(member_dob AS DATE) AS member_dob,
       policy_ref,
       coalesce(nullif(trim(agent_npn), ''), '(blank)') AS agent_npn,
       CAST(amount AS DECIMAL(12, 2)) AS amount,
       _source_file, _row_number, _raw_hash
FROM raw_commission_lines;

-- A name key keeps lower case letters only, so "Ann  Lee" and "ann lee" agree.
CREATE OR REPLACE MACRO name_key(full_name) AS regexp_replace(lower(full_name), '[^a-z]', '', 'g');

CREATE OR REPLACE VIEW book_people AS
SELECT DISTINCT b.policy_id, b.carrier,
       name_key(c.first_name || ' ' || c.last_name) AS person,
       TRY_CAST(c.dob AS DATE) AS dob
FROM book AS b
JOIN raw_clients AS c ON c.client_id = b.client_id;

-- Each line tries three keys in order and keeps the first that works:
--   1. MEMBER_ID: same carrier and carrier_member_id (the strong key)
--   2. POLICY_REF: the policy id the carrier printed
--   3. NAME_DOB: same carrier, name, and date of birth (a weak match, TIE-006)
-- A line no key can place has policy_id NULL: an orphan payment (TIE-002).
CREATE OR REPLACE VIEW line_match AS
WITH by_member AS (
    SELECT s._row_number, min(b.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book AS b ON b.carrier = s.carrier AND b.carrier_member_id = s.carrier_member_id
    GROUP BY s._row_number
),
by_ref AS (
    SELECT s._row_number, min(b.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book AS b ON b.policy_id = s.policy_ref
    GROUP BY s._row_number
),
by_name AS (
    SELECT s._row_number, min(p.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book_people AS p
      ON p.carrier = s.carrier AND p.person = name_key(s.member_name) AND p.dob = s.member_dob
    GROUP BY s._row_number
)
SELECT s.*,
       coalesce(m.policy_id, r.policy_id, n.policy_id) AS policy_id,
       CASE WHEN m.policy_id IS NOT NULL THEN 'MEMBER_ID'
            WHEN r.policy_id IS NOT NULL THEN 'POLICY_REF'
            WHEN n.policy_id IS NOT NULL THEN 'NAME_DOB' END AS match_method
FROM statement_lines AS s
LEFT JOIN by_member AS m USING (_row_number)
LEFT JOIN by_ref AS r USING (_row_number)
LEFT JOIN by_name AS n USING (_row_number);
