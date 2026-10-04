-- 05 Expected amounts from the rate table. A policy pays NEW for its first
-- new_business_months months in force, RENEWAL after that, at the monthly rate for its line
-- of business. A NULL expected (no rate) is never guessed and never flagged.

CREATE OR REPLACE VIEW rate_table AS
SELECT line_of_business, commission_type, CAST(monthly_amount AS DECIMAL(12, 2)) AS monthly_amount
FROM rates;

CREATE OR REPLACE MACRO commission_type_at(effective, period_start, new_months) AS
    CASE WHEN (year(period_start) - year(effective)) * 12
              + month(period_start) - month(effective) < new_months
         THEN 'NEW' ELSE 'RENEWAL' END;

-- What each due policy should be paid in each period (leg A and the totals).
CREATE OR REPLACE VIEW due_expected AS
SELECT d.*, r.monthly_amount AS expected
FROM leg_book_vs_statement AS d
CROSS JOIN tolerances AS t
LEFT JOIN rate_table AS r
  ON r.line_of_business = d.line_of_business
 AND r.commission_type = commission_type_at(d.effective_date, d.period_start, t.new_business_months);

-- What each matched statement line should have paid (the TIE-003 dollar check).
CREATE OR REPLACE VIEW line_expected AS
SELECT l.*, r.monthly_amount AS expected
FROM line_match AS l
JOIN book AS b USING (policy_id)
CROSS JOIN tolerances AS t
LEFT JOIN rate_table AS r
  ON r.line_of_business = b.line_of_business
 AND r.commission_type = commission_type_at(b.effective_date, l.period_start, t.new_business_months);
