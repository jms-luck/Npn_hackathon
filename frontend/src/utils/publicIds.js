function formatId(prefix, value) {
  if (value == null || value === "") return "--";
  const text = String(value);
  if (text.startsWith(`${prefix}_`)) return text;
  return `${prefix}_${text.padStart(3, "0")}`;
}

export const formatCompanyId = value => formatId("COMP", value);
export const formatUserId = value => formatId("USER", value);
export const formatJobId = value => formatId("JOB", value);
export const formatCandidateId = value => formatId("CAND", value);
export const formatRecruiterId = value => formatId("REC", value);
export const formatInterviewerId = value => formatId("INT", value);
export const formatApplicationId = value => formatId("APP", value);
