args <- commandArgs(trailingOnly = TRUE)

read_arg <- function(name, default = "") {
  index <- match(name, args)
  if (is.na(index)) {
    return(default)
  }
  if (index == length(args)) {
    return(default)
  }
  args[[index + 1]]
}

json_quote <- function(value) {
  escaped <- gsub("\\\\", "\\\\\\\\", value)
  escaped <- gsub("\"", "\\\\\"", escaped)
  escaped <- gsub("\n", "\\\\n", escaped)
  paste0("\"", escaped, "\"")
}

prompt <- read_arg("--prompt", "")
workspace_record_count <- as.integer(read_arg("--workspace-record-count", "0"))
workspace_patient_count <- as.integer(read_arg("--workspace-patient-count", "0"))
scope_a_record_count <- as.integer(read_arg("--scope-a-record-count", "0"))
scope_a_patient_count <- as.integer(read_arg("--scope-a-patient-count", "0"))
scope_b_record_count <- as.integer(read_arg("--scope-b-record-count", "0"))
scope_b_patient_count <- as.integer(read_arg("--scope-b-patient-count", "0"))
compare_mode <- identical(tolower(read_arg("--compare-mode", "false")), "true")

reply_lines <- c(
  "### External R scope snapshot",
  "",
  sprintf("- Workspace records: %d", workspace_record_count),
  sprintf("- Workspace patients: %d", workspace_patient_count),
  sprintf("- Cohort A records in scope: %d", scope_a_record_count),
  sprintf("- Cohort A patients in scope: %d", scope_a_patient_count)
)
if (compare_mode) {
  reply_lines <- c(
    reply_lines,
    sprintf("- Cohort B records in scope: %d", scope_b_record_count),
    sprintf("- Cohort B patients in scope: %d", scope_b_patient_count)
  )
}
reply_lines <- c(
  reply_lines,
  "",
  "This is a curated external Rscript analysis used to validate external runner integration."
)
reply <- paste(reply_lines, collapse = "\n")

json <- paste0(
  "{",
  "\"reply\":", json_quote(reply), ",",
  "\"context\":{",
  "\"mode\":\"external_rscript\",",
  "\"runner\":\"dummy_scope_snapshot\",",
  "\"prompt\":", json_quote(prompt), ",",
  "\"workspace_record_count\":", workspace_record_count, ",",
  "\"workspace_patient_count\":", workspace_patient_count, ",",
  "\"scope_a_record_count\":", scope_a_record_count, ",",
  "\"scope_a_patient_count\":", scope_a_patient_count, ",",
  "\"scope_b_record_count\":", scope_b_record_count, ",",
  "\"scope_b_patient_count\":", scope_b_patient_count, ",",
  "\"compare_mode\":", ifelse(compare_mode, "true", "false"),
  "}",
  "}"
)

cat(json)
