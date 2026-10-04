-- 02 Leg A, book vs statement: every active policy should be paid in each period.
-- A period counts for a carrier only when that carrier sent a statement for it; a whole
-- missing statement is a completeness problem (CMP-002), not thousands of unpaid policies.

CREATE OR REPLACE VIEW statement_periods AS
SELECT DISTINCT carrier, statement_period, period_start FROM statement_lines;

-- What the book says is due: ACTIVE policies in force during a statement period.
CREATE OR REPLACE VIEW book_due AS
SELECT b.*, p.statement_period, p.period_start
FROM book AS b
JOIN statement_periods AS p ON p.carrier = b.carrier
WHERE b.status = 'ACTIVE'
  AND b.effective_date <= last_day(p.period_start)
  AND (b.termination_date IS NULL OR b.termination_date >= p.period_start);

-- is_paid is false for an unpaid policy (TIE-001). weak means every line that paid it was
-- matched on name plus DOB only.
CREATE OR REPLACE VIEW leg_book_vs_statement AS
SELECT d.*,
       l.policy_id IS NOT NULL AS is_paid,
       coalesce(l.only_weak, false) AS weak
FROM book_due AS d
LEFT JOIN (
    SELECT policy_id, statement_period, bool_and(match_method = 'NAME_DOB') AS only_weak
    FROM line_match
    WHERE policy_id IS NOT NULL
    GROUP BY policy_id, statement_period
) AS l USING (policy_id, statement_period);
