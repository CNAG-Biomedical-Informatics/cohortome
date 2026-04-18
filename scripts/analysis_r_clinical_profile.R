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

read_tsv <- function(path, columns) {
  if (!nzchar(path) || !file.exists(path)) {
    return(as.data.frame(setNames(replicate(length(columns), character(0), simplify = FALSE), columns), stringsAsFactors = FALSE))
  }
  read.delim(path, sep = "\t", header = TRUE, stringsAsFactors = FALSE, check.names = FALSE)
}

top_label <- function(frame) {
  if (nrow(frame) < 1) {
    return("n/a")
  }
  as.character(frame$label[[1]])
}

top_count <- function(frame) {
  if (nrow(frame) < 1) {
    return(0)
  }
  as.integer(frame$patient_count[[1]])
}

prompt <- read_arg("--prompt", "")
overview_tsv <- read_arg("--overview-tsv", "")
diseases_tsv <- read_arg("--diseases-tsv", "")
medications_tsv <- read_arg("--medications-tsv", "")
periods_tsv <- read_arg("--periods-tsv", "")
compare_mode <- identical(tolower(read_arg("--compare-mode", "false")), "true")

overview <- read_tsv(overview_tsv, c("cohort", "record_count", "patient_count"))
diseases <- read_tsv(diseases_tsv, c("cohort", "label", "patient_count"))
medications <- read_tsv(medications_tsv, c("cohort", "label", "patient_count"))
periods <- read_tsv(periods_tsv, c("cohort", "period", "timepoint_count", "patient_count"))

cohort_a_overview <- overview[overview$cohort == "A", , drop = FALSE]
cohort_b_overview <- overview[overview$cohort == "B", , drop = FALSE]
cohort_a_diseases <- diseases[diseases$cohort == "A", , drop = FALSE]
cohort_b_diseases <- diseases[diseases$cohort == "B", , drop = FALSE]
cohort_a_medications <- medications[medications$cohort == "A", , drop = FALSE]
cohort_b_medications <- medications[medications$cohort == "B", , drop = FALSE]
cohort_a_periods <- periods[periods$cohort == "A", , drop = FALSE]
cohort_b_periods <- periods[periods$cohort == "B", , drop = FALSE]

cohort_a_patients <- if (nrow(cohort_a_overview) >= 1) as.integer(cohort_a_overview$patient_count[[1]]) else 0
cohort_a_records <- if (nrow(cohort_a_overview) >= 1) as.integer(cohort_a_overview$record_count[[1]]) else 0
cohort_b_patients <- if (nrow(cohort_b_overview) >= 1) as.integer(cohort_b_overview$patient_count[[1]]) else 0
cohort_b_records <- if (nrow(cohort_b_overview) >= 1) as.integer(cohort_b_overview$record_count[[1]]) else 0

cohort_a_disease <- top_label(cohort_a_diseases)
cohort_a_disease_count <- top_count(cohort_a_diseases)
cohort_a_medication <- top_label(cohort_a_medications)
cohort_a_medication_count <- top_count(cohort_a_medications)

cohort_b_disease <- top_label(cohort_b_diseases)
cohort_b_disease_count <- top_count(cohort_b_diseases)
cohort_b_medication <- top_label(cohort_b_medications)
cohort_b_medication_count <- top_count(cohort_b_medications)

cohort_a_peak_period <- if (nrow(cohort_a_periods) >= 1) as.character(cohort_a_periods$period[[which.max(cohort_a_periods$timepoint_count)]]) else "n/a"
cohort_b_peak_period <- if (nrow(cohort_b_periods) >= 1) as.character(cohort_b_periods$period[[which.max(cohort_b_periods$timepoint_count)]]) else "n/a"

reply_lines <- c(
  "### External R clinical scope profile",
  "",
  sprintf("- Cohort A patients: %d", cohort_a_patients),
  sprintf("- Cohort A records: %d", cohort_a_records),
  sprintf("- Cohort A top disease: %s (%d patients)", cohort_a_disease, cohort_a_disease_count),
  sprintf("- Cohort A top medication: %s (%d patients)", cohort_a_medication, cohort_a_medication_count),
  sprintf("- Cohort A most active period: %s", cohort_a_peak_period)
)

if (compare_mode) {
  reply_lines <- c(
    reply_lines,
    "",
    sprintf("- Cohort B patients: %d", cohort_b_patients),
    sprintf("- Cohort B records: %d", cohort_b_records),
    sprintf("- Cohort B top disease: %s (%d patients)", cohort_b_disease, cohort_b_disease_count),
    sprintf("- Cohort B top medication: %s (%d patients)", cohort_b_medication, cohort_b_medication_count),
    sprintf("- Cohort B most active period: %s", cohort_b_peak_period)
  )
}

reply_lines <- c(
  reply_lines,
  "",
  "This summary was produced by a curated external Rscript from scoped clinical tables prepared by the app."
)

reply <- paste(reply_lines, collapse = "\n")

json <- paste0(
  "{",
  "\"reply\":", json_quote(reply), ",",
  "\"context\":{",
  "\"mode\":\"external_rscript_profile\",",
  "\"runner\":\"clinical_scope_profile\",",
  "\"prompt\":", json_quote(prompt), ",",
  "\"compare_mode\":", ifelse(compare_mode, "true", "false"), ",",
  "\"cohort_a_patient_count\":", cohort_a_patients, ",",
  "\"cohort_a_record_count\":", cohort_a_records, ",",
  "\"cohort_a_top_disease\":", json_quote(cohort_a_disease), ",",
  "\"cohort_a_top_disease_count\":", cohort_a_disease_count, ",",
  "\"cohort_a_top_medication\":", json_quote(cohort_a_medication), ",",
  "\"cohort_a_top_medication_count\":", cohort_a_medication_count, ",",
  "\"cohort_a_peak_period\":", json_quote(cohort_a_peak_period), ",",
  "\"cohort_b_patient_count\":", cohort_b_patients, ",",
  "\"cohort_b_record_count\":", cohort_b_records, ",",
  "\"cohort_b_top_disease\":", json_quote(cohort_b_disease), ",",
  "\"cohort_b_top_disease_count\":", cohort_b_disease_count, ",",
  "\"cohort_b_top_medication\":", json_quote(cohort_b_medication), ",",
  "\"cohort_b_top_medication_count\":", cohort_b_medication_count, ",",
  "\"cohort_b_peak_period\":", json_quote(cohort_b_peak_period),
  "}",
  "}"
)

cat(json)
