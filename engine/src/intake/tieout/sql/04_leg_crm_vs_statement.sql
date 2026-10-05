-- 04 Leg C, CRM vs statement: a policy the carrier pays should be ACTIVE in the CRM.
-- One row per paid policy, pointing at its latest statement line. agrees is false for a
-- status conflict (TIE-004), for example a CRM that says CANCELLED while the carrier pays.
-- A chargeback is the carrier taking money back, never paying, so it is left out here.
CREATE OR REPLACE VIEW leg_crm_vs_statement AS
SELECT b.policy_id, b.carrier, b.carrier_member_id, b.agent_npn, b.status,
       b._rec,
       max(l.statement_period) AS statement_period,
       arg_max(l.line_no, l.period_start) AS line_no,
       b.status = 'ACTIVE' AS agrees,
       bool_and(l.match_method = 'NAME_DOB') AS weak
FROM line_match AS l
JOIN book AS b USING (carrier, policy_id)
WHERE NOT l.is_chargeback
GROUP BY ALL;
