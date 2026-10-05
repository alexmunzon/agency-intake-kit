-- 07 Totals by carrier and by agent across all statement periods: what the book expects
-- (every in-force policy at the scheduled rate, periods with no statement included, so a
-- carrier that sent nothing still has a row; plus expected chargebacks at their own amount)
-- vs what the statements paid. Orphan payments
-- inside statement_paid are unexplained revenue. A total is within tolerance when the
-- difference is at most 0.5 percent of the book (else TIE-005, error).
-- The book side groups by the policy's writing agent, the paid side by the agent on the line.
CREATE OR REPLACE VIEW totals AS
WITH book_side AS (
    SELECT carrier, agent_npn, coalesce(expected, 0) AS expected FROM in_force_expected
    UNION ALL
    SELECT carrier, agent_npn, amount FROM line_expected WHERE expected_chargeback
),
book_keyed AS (
    SELECT 'carrier' AS group_by, carrier AS key, expected FROM book_side
    UNION ALL
    SELECT 'agent', agent_npn, expected FROM book_side
),
paid_side AS (
    SELECT 'carrier' AS group_by, carrier AS key, amount, policy_id IS NULL AS orphan
    FROM line_match
    UNION ALL
    SELECT 'agent', agent_npn, amount, policy_id IS NULL FROM line_match
),
book_totals AS (
    SELECT group_by, key, sum(expected) AS book_expected FROM book_keyed GROUP BY ALL
),
paid_totals AS (
    SELECT group_by, key, sum(amount) AS statement_paid,
           sum(CASE WHEN orphan THEN amount ELSE 0 END) AS unexplained_revenue
    FROM paid_side GROUP BY ALL
),
joined AS (
    SELECT group_by, key,
           CAST(coalesce(book_expected, 0) AS DECIMAL(12, 2)) AS book_expected,
           CAST(coalesce(statement_paid, 0) AS DECIMAL(12, 2)) AS statement_paid,
           CAST(coalesce(unexplained_revenue, 0) AS DECIMAL(12, 2)) AS unexplained_revenue
    FROM book_totals FULL OUTER JOIN paid_totals USING (group_by, key)
)
SELECT group_by, key, book_expected, statement_paid,
       statement_paid - book_expected AS difference,
       unexplained_revenue,
       abs(statement_paid - book_expected) <= abs(book_expected) * t.total_pct AS within_tolerance
FROM joined CROSS JOIN tolerances AS t
ORDER BY group_by, key;
