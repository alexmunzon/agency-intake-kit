-- 05 Expected amounts from the rate table. A policy pays NEW for its first
-- new_business_months months in force, RENEWAL after that, at the monthly rate for its line
-- of business. A NULL expected (no rate) is never guessed and never flagged. An OVERRIDE line
-- is checked against an OVERRIDE rate only when the rate table has one.

CREATE OR REPLACE VIEW rate_table AS
SELECT line_of_business, commission_type, CAST(monthly_amount AS DECIMAL(12, 2)) AS monthly_amount
FROM rates;

CREATE OR REPLACE MACRO commission_type_at(effective, period_start, new_months) AS
    CASE WHEN (year(period_start) - year(effective)) * 12
              + month(period_start) - month(effective) < new_months
         THEN 'NEW' ELSE 'RENEWAL' END;

-- What each in-force policy should be paid in each period (leg A, missing statements, totals).
CREATE OR REPLACE VIEW in_force_expected AS
SELECT d.*, r.monthly_amount AS expected
FROM book_in_force AS d
CROSS JOIN tolerances AS t
LEFT JOIN rate_table AS r
  ON r.line_of_business = d.line_of_business
 AND r.commission_type = commission_type_at(d.effective_date, d.period_start, t.new_business_months);

CREATE OR REPLACE VIEW due_expected AS
SELECT d.*, e.expected
FROM leg_book_vs_statement AS d
JOIN in_force_expected AS e USING (carrier, policy_id, statement_period);

-- A carrier and period the book expected money for, with no statement at all.
CREATE OR REPLACE VIEW missing_statements AS
SELECT carrier, statement_period, count(*) AS policies,
       CAST(sum(coalesce(expected, 0)) AS DECIMAL(12, 2)) AS expected
FROM in_force_expected WHERE NOT has_statement
GROUP BY ALL;

-- What each matched statement line should have paid (the TIE-003 dollar check).
-- expected_chargeback: a clawback on a policy that is CANCELLED or TERMINATED, or ended by the
-- end of the line's period. The carrier and the book agree, so it is never a variance. A
-- chargeback on a policy still in force is compared to the schedule like any line.
CREATE OR REPLACE VIEW line_expected AS
SELECT l.*, r.monthly_amount AS expected,
       l.is_chargeback AND (b.status IN ('CANCELLED', 'TERMINATED')
                            OR coalesce(b.termination_date <= last_day(l.period_start), false))
           AS expected_chargeback
FROM line_match AS l
JOIN book AS b USING (carrier, policy_id)
CROSS JOIN tolerances AS t
LEFT JOIN rate_table AS r
  ON r.line_of_business = b.line_of_business
 AND r.commission_type = CASE WHEN l.commission_type = 'OVERRIDE' THEN 'OVERRIDE'
     ELSE commission_type_at(b.effective_date, l.period_start, t.new_business_months) END;
