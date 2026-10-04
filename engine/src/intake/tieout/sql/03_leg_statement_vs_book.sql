-- 03 Leg B, statement vs book: every commission line should belong to a policy in the book.
-- An unmatched line is an orphan payment (TIE-002), counted as unexplained revenue.
CREATE OR REPLACE VIEW leg_statement_vs_book AS
SELECT *,
       policy_id IS NOT NULL AS is_matched,
       coalesce(match_method = 'NAME_DOB', false) AS weak
FROM line_match;
