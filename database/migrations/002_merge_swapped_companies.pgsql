UPDATE job_postings AS job
SET company_id = good.company_id
FROM companies AS bad
JOIN companies AS good
  ON good.company_name = bad.company_size
 AND good.company_id != bad.company_id
WHERE job.company_id = bad.company_id
  AND bad.company_name ~ '^[0-9]+$'
  AND bad.company_size IS NOT NULL
  AND bad.company_size !~ '^[0-9]+$';

UPDATE recruiters AS recruiter
SET company_id = good.company_id
FROM companies AS bad
JOIN companies AS good
  ON good.company_name = bad.company_size
 AND good.company_id != bad.company_id
WHERE recruiter.company_id = bad.company_id
  AND bad.company_name ~ '^[0-9]+$'
  AND bad.company_size IS NOT NULL
  AND bad.company_size !~ '^[0-9]+$';

UPDATE interviewers AS interviewer
SET company_id = good.company_id
FROM companies AS bad
JOIN companies AS good
  ON good.company_name = bad.company_size
 AND good.company_id != bad.company_id
WHERE interviewer.company_id = bad.company_id
  AND bad.company_name ~ '^[0-9]+$'
  AND bad.company_size IS NOT NULL
  AND bad.company_size !~ '^[0-9]+$';

DELETE FROM companies AS bad
USING companies AS good
WHERE good.company_name = bad.company_size
  AND good.company_id != bad.company_id
  AND bad.company_name ~ '^[0-9]+$'
  AND bad.company_size IS NOT NULL
  AND bad.company_size !~ '^[0-9]+$';
