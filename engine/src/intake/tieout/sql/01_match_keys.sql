-- 01 Match keys: type the text, then tie each commission line to one policy in the book.
-- Money is DECIMAL(12,2) everywhere, never a float, so cents are never lost. prepare.py has
-- already read dates (ISO), periods (YYYY-MM), and amounts (plain decimals), so a cast here
-- only fails on a value prepare.py counted as unreadable, and that value is NULL, never a crash.
-- _rec is a row's position in its table. It is the only row key: lineage row numbers repeat
-- across statement files, and carrier, period, and line_no repeat when a line is duplicated.

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
           _rec,
           row_number() OVER (PARTITION BY policy_id ORDER BY _rec) AS copy_number
    FROM raw_policies
)
WHERE copy_number = 1;

-- Statement lines as the carrier sent them. A chargeback is a CHARGEBACK line or any negative
-- amount (a clawback). amount is NULL when amount_problem says it was BLANK or NOT_A_NUMBER.
CREATE OR REPLACE VIEW statement_lines AS
SELECT carrier, statement_period,
       TRY_CAST(statement_period || '-01' AS DATE) AS period_start,
       TRY_CAST(line_no AS INTEGER) AS line_no,
       carrier_member_id, member_name,
       TRY_CAST(member_dob AS DATE) AS member_dob,
       policy_ref,
       coalesce(nullif(trim(agent_npn), ''), '(blank)') AS agent_npn,
       TRY_CAST(amount AS DECIMAL(12, 2)) AS amount,
       amount_problem,
       upper(trim(commission_type)) AS commission_type,
       coalesce(upper(trim(commission_type)) = 'CHARGEBACK', false)
           OR coalesce(TRY_CAST(amount AS DECIMAL(12, 2)) < 0, false) AS is_chargeback,
       _rec
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
    SELECT s._rec, min(b.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book AS b ON b.carrier = s.carrier AND b.carrier_member_id = s.carrier_member_id
    GROUP BY s._rec
),
by_ref AS (
    SELECT s._rec, min(b.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book AS b ON b.policy_id = s.policy_ref
    GROUP BY s._rec
),
by_name AS (
    SELECT s._rec, min(p.policy_id) AS policy_id
    FROM statement_lines AS s
    JOIN book_people AS p
      ON p.carrier = s.carrier AND p.person = name_key(s.member_name) AND p.dob = s.member_dob
    GROUP BY s._rec
)
SELECT s.*,
       coalesce(m.policy_id, r.policy_id, n.policy_id) AS policy_id,
       CASE WHEN m.policy_id IS NOT NULL THEN 'MEMBER_ID'
            WHEN r.policy_id IS NOT NULL THEN 'POLICY_REF'
            WHEN n.policy_id IS NOT NULL THEN 'NAME_DOB' END AS match_method
FROM statement_lines AS s
LEFT JOIN by_member AS m USING (_rec)
LEFT JOIN by_ref AS r USING (_rec)
LEFT JOIN by_name AS n USING (_rec);
