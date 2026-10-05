-- 02 Leg A, book vs statement: every active policy should be paid in each period.
-- The run's periods are every period any carrier sent. A policy whose carrier sent no statement
-- for a period is not called unpaid (that would be thousands of TIE-001s for one missing file):
-- has_statement is false, and 06_variances.sql reports the carrier and period once, as a
-- missing statement (TIE-005), with what the book expected.

CREATE OR REPLACE VIEW statement_periods AS
SELECT DISTINCT carrier, statement_period, period_start
FROM statement_lines WHERE period_start IS NOT NULL;

CREATE OR REPLACE VIEW run_periods AS
SELECT DISTINCT statement_period, period_start FROM statement_periods;

-- What the book says is due: ACTIVE policies in force during a run period.
CREATE OR REPLACE VIEW book_in_force AS
SELECT b.*, p.statement_period, p.period_start, s.carrier IS NOT NULL AS has_statement
FROM book AS b
CROSS JOIN run_periods AS p
LEFT JOIN statement_periods AS s
  ON s.carrier = b.carrier AND s.statement_period = p.statement_period
WHERE b.status = 'ACTIVE'
  AND b.effective_date <= last_day(p.period_start)
  AND (b.termination_date IS NULL OR b.termination_date >= p.period_start);

CREATE OR REPLACE VIEW book_due AS
SELECT * EXCLUDE (has_statement) FROM book_in_force WHERE has_statement;

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
