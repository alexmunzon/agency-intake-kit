-- 06 Variances: every finding with its reason code, rule, and the record it points at.
--   NO_PAYMENT          TIE-001  leg A  active policy unpaid in a period
--   ORPHAN_PAYMENT      TIE-002  leg B  line for a member no policy has
--   AMOUNT_OFF_SCHEDULE TIE-003  none   paid vs expected beyond the larger of $1 or 1 percent
--   AMOUNT_BLANK        TIE-003  none   the line has no amount (never silently dropped)
--   AMOUNT_NOT_A_NUMBER TIE-003  none   the amount is not a number (one finding, never a crash)
--   STATUS_CONFLICT     TIE-004  leg C  carrier pays, CRM status is not ACTIVE
--   MISSING_STATEMENT   TIE-005  none   the book expected money from a carrier for a period
--                                       and that carrier sent no statement for it
--   WEAK_MATCH          TIE-006  none   line matched on name plus DOB only (info)
-- Totals (TIE-005 TOTAL_OFF) are in 07_totals.sql. paid or expected is NULL when missing.
-- source and _rec point at the row; variances.py carries that row's own lineage.
CREATE OR REPLACE VIEW variances AS
SELECT 'TIE-001' AS rule_id, 'NO_PAYMENT' AS reason_code, carrier, statement_period,
       NULL::INTEGER AS line_no, policy_id, carrier_member_id, agent_npn,
       NULL::DECIMAL(12, 2) AS paid, expected,
       'policies' AS source, 'policy_id' AS field, policy_id AS raw_value, _rec
FROM due_expected WHERE NOT is_paid
UNION ALL
SELECT 'TIE-002', CASE WHEN link_state = 'unmatched' THEN 'ORPHAN_PAYMENT'
                      ELSE 'UNRESOLVED_LINK' END, carrier, statement_period, line_no, NULL,
       carrier_member_id, agent_npn, amount, NULL,
       'commission_lines', 'carrier_member_id', carrier_member_id, _rec
FROM leg_statement_vs_book WHERE NOT is_matched
UNION ALL
SELECT 'TIE-003', 'AMOUNT_OFF_SCHEDULE', carrier, statement_period, line_no, policy_id,
       carrier_member_id, agent_npn, amount, expected,
       'commission_lines', 'amount', CAST(amount AS VARCHAR), _rec
FROM line_expected CROSS JOIN tolerances AS t
WHERE NOT expected_chargeback
  AND abs(amount - expected) > greatest(t.line_usd, expected * t.line_pct)
UNION ALL
SELECT 'TIE-003', 'AMOUNT_' || l.amount_problem, l.carrier, l.statement_period, l.line_no,
       l.policy_id, l.carrier_member_id, l.agent_npn, NULL, e.expected,
       'commission_lines', 'amount', r.amount_raw, l._rec
FROM line_match AS l
JOIN raw_commission_lines AS r USING (_rec)
LEFT JOIN line_expected AS e USING (_rec)
WHERE l.amount_problem IS NOT NULL
UNION ALL
SELECT 'TIE-004', 'STATUS_CONFLICT', carrier, statement_period, line_no, policy_id,
       carrier_member_id, agent_npn, NULL, NULL,
       'policies', 'status', status, _rec
FROM leg_crm_vs_statement WHERE NOT agrees
UNION ALL
SELECT 'TIE-005', 'MISSING_STATEMENT', carrier, statement_period, NULL, NULL,
       NULL, NULL, NULL, expected,
       'commission_lines', 'carrier', carrier, NULL
FROM missing_statements
UNION ALL
SELECT 'TIE-006', 'WEAK_MATCH', carrier, statement_period, line_no, policy_id,
       carrier_member_id, agent_npn, amount, NULL,
       'commission_lines', 'member_name', member_name, _rec
FROM leg_statement_vs_book WHERE weak
ORDER BY rule_id, carrier, statement_period, line_no, policy_id;

-- Leg counts. matched + unmatched is everything the leg checked; weak_matched is the part
-- of matched made on name plus DOB only.
CREATE OR REPLACE VIEW leg_counts AS
SELECT 'BOOK_VS_STATEMENT' AS leg, count(*) FILTER (is_paid) AS matched,
       count(*) FILTER (NOT is_paid) AS unmatched, count(*) FILTER (is_paid AND weak) AS weak_matched
FROM leg_book_vs_statement
UNION ALL
SELECT 'STATEMENT_VS_BOOK', count(*) FILTER (is_matched), count(*) FILTER (NOT is_matched),
       count(*) FILTER (weak AND is_matched)
FROM leg_statement_vs_book
UNION ALL
SELECT 'CRM_VS_STATEMENT', count(*) FILTER (agrees), count(*) FILTER (NOT agrees),
       count(*) FILTER (agrees AND weak)
FROM leg_crm_vs_statement;
