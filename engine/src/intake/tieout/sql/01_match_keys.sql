-- 01 Match keys: type the text, then retain every policy candidate for each statement line.
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

-- The book: one row per carrier and policy_id. A duplicated policy (DUP-001, DUP-003)
-- keeps its first row within that carrier, so a copy never doubles expected payment.
-- Different carriers may legitimately reuse the same policy_id.
CREATE OR REPLACE VIEW book AS
SELECT * EXCLUDE (copy_number)
FROM (
    SELECT policy_id, client_id, carrier, carrier_member_id, line_of_business,
           TRY_CAST(effective_date AS DATE) AS effective_date,
           TRY_CAST(termination_date AS DATE) AS termination_date,
           upper(trim(status)) AS status,
           coalesce(nullif(trim(writing_agent_npn), ''), '(blank)') AS agent_npn,
           _rec,
           row_number() OVER (PARTITION BY carrier, policy_id ORDER BY _rec) AS copy_number
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
SELECT DISTINCT b.policy_id, b._rec AS policy_rec, b.carrier,
       name_key(c.first_name || ' ' || c.last_name) AS person,
       TRY_CAST(c.dob AS DATE) AS dob
FROM book AS b
JOIN raw_clients AS c ON c.client_id = b.client_id;

-- Candidate edges preserve all matching evidence. policy_rec points to the deduplicated book
-- row, so downstream output can recover its lineage. Blank identifiers and empty name keys
-- do not match each other. A policy reference must agree on carrier as well as policy ID.
CREATE OR REPLACE VIEW line_candidates AS
SELECT DISTINCT s._rec, b.policy_id, b._rec AS policy_rec, 'MEMBER_ID' AS match_method
FROM statement_lines AS s
JOIN book AS b ON b.carrier = s.carrier
              AND trim(b.carrier_member_id) = trim(s.carrier_member_id)
WHERE nullif(trim(s.carrier), '') IS NOT NULL
  AND nullif(trim(s.carrier_member_id), '') IS NOT NULL
  AND nullif(trim(b.carrier_member_id), '') IS NOT NULL
UNION ALL
SELECT DISTINCT s._rec, b.policy_id, b._rec AS policy_rec, 'POLICY_REF' AS match_method
FROM statement_lines AS s
JOIN book AS b ON b.carrier = s.carrier AND trim(b.policy_id) = trim(s.policy_ref)
WHERE nullif(trim(s.carrier), '') IS NOT NULL
  AND nullif(trim(s.policy_ref), '') IS NOT NULL
UNION ALL
SELECT DISTINCT s._rec, p.policy_id, p.policy_rec, 'NAME_DOB' AS match_method
FROM statement_lines AS s
JOIN book_people AS p ON p.carrier = s.carrier
                     AND p.person = name_key(s.member_name)
                     AND p.dob = s.member_dob
WHERE nullif(trim(s.carrier), '') IS NOT NULL
  AND nullif(name_key(s.member_name), '') IS NOT NULL
  AND nullif(p.person, '') IS NOT NULL
  AND s.member_dob IS NOT NULL;

-- One output row per statement _rec. A unique strong candidate remains confirmed when
-- name/DOB also includes that candidate, even if other people share the name/DOB. A weak
-- candidate set that excludes it is contradictory, with one narrow exception: when the strong
-- policy has no client row at all (an orphan policy, REF-001) its person is unknown, and if
-- the line matched it by BOTH member ID and policy reference, name/DOB evidence for other
-- policies cannot disagree with it, so the line is confirmed by its strong keys. One strong
-- key alone is not enough. A client row that exists, even with a blank name, is a known
-- person. Policy client_id is compared as text: a blank client_id joins a blank client row
-- and so counts as known (errs toward a conflict), while a NULL client_id joins nothing and
-- counts as unknown. All edges stay available for review.
-- max(policy_id) is read only when its distinct strong count is one, never as a tie breaker.
CREATE OR REPLACE VIEW line_match AS
WITH candidate_counts AS (
    SELECT _rec, count(DISTINCT policy_id) AS candidate_count,
           count(DISTINCT policy_id) FILTER (
               WHERE match_method IN ('MEMBER_ID', 'POLICY_REF')) AS strong_candidate_count,
           count(DISTINCT policy_id) FILTER (
               WHERE match_method = 'NAME_DOB') AS weak_candidate_count,
           max(policy_id) FILTER (
               WHERE match_method IN ('MEMBER_ID', 'POLICY_REF')) AS sole_strong_policy_id,
           count(*) FILTER (WHERE match_method = 'MEMBER_ID') > 0 AS strong_member_matched,
           count(*) FILTER (WHERE match_method = 'POLICY_REF') > 0 AS strong_ref_matched
    FROM line_candidates
    GROUP BY _rec
),
evidence AS (
    SELECT s.*,
           coalesce(c.candidate_count, 0) AS candidate_count,
           coalesce(c.strong_candidate_count, 0) AS strong_candidate_count,
           coalesce(c.weak_candidate_count, 0) AS weak_candidate_count,
           c.sole_strong_policy_id,
           nullif(trim(s.carrier_member_id), '') IS NOT NULL AS strong_member_supplied,
           nullif(trim(s.policy_ref), '') IS NOT NULL AS strong_ref_supplied,
           coalesce(c.strong_member_matched, false) AS strong_member_matched,
           coalesce(c.strong_ref_matched, false) AS strong_ref_matched,
           EXISTS (
               SELECT 1 FROM line_candidates AS w
               WHERE w._rec = s._rec AND w.match_method = 'NAME_DOB'
                 AND w.policy_id = c.sole_strong_policy_id
           ) AS weak_includes_strong,
           EXISTS (
               SELECT 1 FROM line_candidates AS k
               JOIN book_people AS p ON p.policy_rec = k.policy_rec
               WHERE k._rec = s._rec AND k.match_method IN ('MEMBER_ID', 'POLICY_REF')
                 AND k.policy_id = c.sole_strong_policy_id
           ) AS strong_person_known
    FROM statement_lines AS s
    LEFT JOIN candidate_counts AS c USING (_rec)
),
classified AS (
    SELECT *, CASE
        WHEN candidate_count = 0 THEN 'no_candidate'
        WHEN strong_candidate_count > 1 THEN 'multiple_candidates'
        WHEN (strong_member_supplied AND NOT strong_member_matched)
          OR (strong_ref_supplied AND NOT strong_ref_matched) THEN 'unmatched_strong_key'
        WHEN strong_candidate_count = 1 AND weak_candidate_count > 0
          AND NOT weak_includes_strong
          AND (strong_person_known OR NOT (strong_member_matched AND strong_ref_matched))
          THEN 'conflicting_name_dob'
        WHEN strong_candidate_count = 1 THEN 'strong_key'
        WHEN weak_candidate_count > 1 THEN 'multiple_candidates'
        ELSE 'name_dob_only' END AS link_reason
    FROM evidence
),
states AS (
    SELECT *, CASE link_reason
        WHEN 'strong_key' THEN 'confirmed'
        WHEN 'name_dob_only' THEN 'provisional'
        WHEN 'no_candidate' THEN 'unmatched'
        ELSE 'ambiguous' END AS link_state
    FROM classified
)
SELECT * EXCLUDE (sole_strong_policy_id),
       CASE WHEN link_state = 'confirmed' THEN sole_strong_policy_id END AS policy_id,
       CASE WHEN link_state = 'confirmed' AND strong_member_matched THEN 'MEMBER_ID'
            WHEN link_state = 'confirmed' AND strong_ref_matched THEN 'POLICY_REF'
            WHEN link_state = 'provisional' THEN 'NAME_DOB' END AS match_method
FROM states;
