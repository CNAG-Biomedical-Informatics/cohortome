args <- commandArgs(trailingOnly = TRUE)

arg_value <- function(name, default = "") {
  index <- match(name, args)
  if (is.na(index) || index == length(args)) default else args[[index + 1L]]
}

required_path <- function(name) {
  path <- arg_value(name, "")
  if (!nzchar(path)) {
    stop(sprintf("%s is required.", name))
  }
  path
}

if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("jsonlite is required for quantitative assay comparison.")
}

delimiter_from_name <- function(name) {
  delimiters <- c(tab = "\t", comma = ",", semicolon = ";")
  normalized <- tolower(trimws(name))
  if (!normalized %in% names(delimiters)) {
    stop("The matrix delimiter must be tab, comma, or semicolon.")
  }
  unname(delimiters[[normalized]])
}

read_character_table <- function(path, separator) {
  if (!file.exists(path)) {
    stop("A required quantitative assay input is unavailable.")
  }
  read.table(
    path,
    sep = separator,
    header = TRUE,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    quote = "\"",
    comment.char = "",
    colClasses = "character",
    fill = FALSE
  )
}

write_json_file <- function(path, payload) {
  writeLines(
    jsonlite::toJSON(
      payload,
      auto_unbox = TRUE,
      null = "null",
      na = "null",
      digits = 10,
      pretty = TRUE
    ),
    con = path,
    useBytes = TRUE
  )
}

finite_summary <- function(values) {
  values <- values[is.finite(values)]
  if (!length(values)) {
    return(c(mean = NA_real_, median = NA_real_, q1 = NA_real_, q3 = NA_real_))
  }
  quartiles <- as.numeric(stats::quantile(values, probs = c(0.25, 0.75), names = FALSE, type = 7))
  c(
    mean = mean(values),
    median = stats::median(values),
    q1 = quartiles[[1]],
    q3 = quartiles[[2]]
  )
}

prompt <- arg_value("--prompt", "")
dataset_name <- arg_value("--dataset-name", "")
modality <- arg_value("--modality", "")
data_type <- arg_value("--data-type", "")
matrix_path <- required_path("--matrix")
sample_table_path <- required_path("--sample-table")
results_path <- required_path("--results-table")
summary_path <- required_path("--summary-json")
plot_path <- required_path("--plot-file")
separator <- delimiter_from_name(arg_value("--delimiter-name", ""))

samples <- read_character_table(sample_table_path, "\t")
required_sample_columns <- c("sample_id", "patient_id", "cohort")
if (!all(required_sample_columns %in% names(samples))) {
  stop("The scoped sample table must contain sample_id, patient_id, and cohort columns.")
}
samples <- samples[, required_sample_columns, drop = FALSE]
for (column in required_sample_columns) {
  samples[[column]] <- trimws(as.character(samples[[column]]))
}
if (any(!nzchar(samples$sample_id)) || anyDuplicated(samples$sample_id)) {
  stop("The scoped sample table contains empty or duplicate sample identifiers.")
}
if (any(!nzchar(samples$patient_id)) || anyDuplicated(samples$patient_id)) {
  stop("Quantitative assay comparison requires one non-empty sample per patient.")
}
if (any(!samples$cohort %in% c("A", "B"))) {
  stop("Quantitative assay comparison accepts only Cohort A and Cohort B samples.")
}
cohort_a_sample_count <- sum(samples$cohort == "A")
cohort_b_sample_count <- sum(samples$cohort == "B")
if (cohort_a_sample_count < 3L || cohort_b_sample_count < 3L) {
  stop("Quantitative assay comparison requires at least three samples in each cohort.")
}

matrix_frame <- read_character_table(matrix_path, separator)
if (ncol(matrix_frame) < 3L || nrow(matrix_frame) < 1L) {
  stop("The quantitative assay matrix needs a feature column and at least two sample columns.")
}
names(matrix_frame)[[1]] <- sub("^\ufeff", "", names(matrix_frame)[[1]])
feature_ids <- trimws(as.character(matrix_frame[[1]]))
if (any(!nzchar(feature_ids)) || anyDuplicated(feature_ids)) {
  stop("The quantitative assay matrix contains empty or duplicate feature identifiers.")
}
source_sample_ids <- names(matrix_frame)[-1L]
if (any(!nzchar(source_sample_ids)) || anyDuplicated(source_sample_ids)) {
  stop("The quantitative assay matrix contains empty or duplicate sample identifiers.")
}
selected_positions <- match(samples$sample_id, source_sample_ids)
if (anyNA(selected_positions)) {
  stop("The quantitative assay matrix columns do not align with the scoped sample table.")
}

selected_frame <- matrix_frame[, selected_positions + 1L, drop = FALSE]
numeric_values <- matrix(NA_real_, nrow = nrow(selected_frame), ncol = ncol(selected_frame))
missing_tokens <- c("", "na", "n/a", "nan", "null", "none", ".")
for (column_index in seq_len(ncol(selected_frame))) {
  raw_values <- trimws(as.character(selected_frame[[column_index]]))
  missing <- is.na(raw_values) | tolower(raw_values) %in% missing_tokens
  converted <- suppressWarnings(as.numeric(raw_values))
  if (any(!missing & !is.finite(converted))) {
    stop("The quantitative assay matrix contains a non-numeric or infinite selected value.")
  }
  converted[missing] <- NA_real_
  numeric_values[, column_index] <- converted
}
rownames(numeric_values) <- feature_ids
colnames(numeric_values) <- samples$sample_id

cohort_a_columns <- samples$cohort == "A"
cohort_b_columns <- samples$cohort == "B"
rows <- vector("list", nrow(numeric_values))

for (feature_index in seq_len(nrow(numeric_values))) {
  cohort_a_all <- numeric_values[feature_index, cohort_a_columns]
  cohort_b_all <- numeric_values[feature_index, cohort_b_columns]
  cohort_a <- cohort_a_all[is.finite(cohort_a_all)]
  cohort_b <- cohort_b_all[is.finite(cohort_b_all)]
  cohort_a_stats <- finite_summary(cohort_a)
  cohort_b_stats <- finite_summary(cohort_b)

  status <- "tested"
  p_value <- NA_real_
  effect <- NA_real_
  if (length(cohort_a) < 3L || length(cohort_b) < 3L) {
    status <- "insufficient_complete_cases"
  } else if (length(unique(c(cohort_a, cohort_b))) < 2L) {
    status <- "constant"
  } else {
    test <- stats::wilcox.test(
      cohort_a,
      cohort_b,
      alternative = "two.sided",
      exact = FALSE,
      correct = FALSE
    )
    u_statistic <- as.numeric(test$statistic)
    effect <- (2 * u_statistic) / (length(cohort_a) * length(cohort_b)) - 1
    p_value <- as.numeric(test$p.value)
  }

  rows[[feature_index]] <- data.frame(
    feature_id = feature_ids[[feature_index]],
    status = status,
    cohort_a_n = length(cohort_a),
    cohort_b_n = length(cohort_b),
    cohort_a_missing = length(cohort_a_all) - length(cohort_a),
    cohort_b_missing = length(cohort_b_all) - length(cohort_b),
    cohort_a_mean = cohort_a_stats[["mean"]],
    cohort_a_median = cohort_a_stats[["median"]],
    cohort_a_q1 = cohort_a_stats[["q1"]],
    cohort_a_q3 = cohort_a_stats[["q3"]],
    cohort_b_mean = cohort_b_stats[["mean"]],
    cohort_b_median = cohort_b_stats[["median"]],
    cohort_b_q1 = cohort_b_stats[["q1"]],
    cohort_b_q3 = cohort_b_stats[["q3"]],
    mean_difference = cohort_a_stats[["mean"]] - cohort_b_stats[["mean"]],
    median_difference = cohort_a_stats[["median"]] - cohort_b_stats[["median"]],
    rank_biserial_effect = effect,
    p_value = p_value,
    adj_p_value = NA_real_,
    stringsAsFactors = FALSE
  )
}

result <- do.call(rbind, rows)
tested <- result$status == "tested"
result$adj_p_value[tested] <- stats::p.adjust(result$p_value[tested], method = "BH")
q_order <- ifelse(is.finite(result$adj_p_value), result$adj_p_value, Inf)
effect_order <- ifelse(is.finite(result$rank_biserial_effect), -abs(result$rank_biserial_effect), Inf)
result <- result[order(q_order, effect_order, result$feature_id), , drop = FALSE]
row.names(result) <- NULL

write.table(
  result,
  results_path,
  sep = "\t",
  row.names = FALSE,
  col.names = TRUE,
  quote = FALSE,
  na = "NA"
)

tested_result <- result[result$status == "tested", , drop = FALSE]
significant_feature_count <- sum(tested_result$adj_p_value < 0.05, na.rm = TRUE)
top <- if (nrow(tested_result)) tested_result[1, , drop = FALSE] else NULL

png(plot_path, width = 960, height = 720)
if (nrow(tested_result)) {
  plot_y <- -log10(pmax(tested_result$adj_p_value, 1e-300))
  point_colors <- ifelse(tested_result$adj_p_value < 0.05, "#d9485f", "#64748b")
  plot(
    tested_result$rank_biserial_effect,
    plot_y,
    pch = 16,
    col = point_colors,
    xlim = c(-1, 1),
    xlab = "Rank-biserial effect (Cohort A - Cohort B)",
    ylab = "-log10 BH-adjusted p-value",
    main = sprintf("Exploratory %s comparison", ifelse(nzchar(data_type), data_type, modality))
  )
  abline(v = 0, col = "#475569", lty = 2)
  abline(h = -log10(0.05), col = "#d9485f", lty = 3)
  label_count <- min(5L, nrow(tested_result))
  text(
    tested_result$rank_biserial_effect[seq_len(label_count)],
    plot_y[seq_len(label_count)],
    labels = tested_result$feature_id[seq_len(label_count)],
    pos = 3,
    cex = 0.8,
    col = "#111827"
  )
} else {
  plot.new()
  title(main = sprintf("Exploratory %s comparison", ifelse(nzchar(data_type), data_type, modality)))
  text(0.5, 0.5, "No features met the testing requirements.", col = "#475569")
}
invisible(dev.off())

caveats <- c(
  "No normalization or transformation was applied; effects are on the supplied assay scale.",
  "Each feature used the finite observations available in each cohort; missing measurements were excluded feature by feature.",
  "This is an unadjusted exploratory comparison and does not account for clinical or technical covariates."
)
if (identical(modality, "flow_cytometry")) {
  caveats <- c(caveats, "Immune-cell abundance features may be compositional, so shifts can reflect changes elsewhere in the measured cell mixture.")
} else if (identical(modality, "serology")) {
  caveats <- c(caveats, "Serology missingness can be feature-dependent; compare missing counts between cohorts before interpreting a marker.")
}
summary <- list(
  dataset_name = dataset_name,
  modality = modality,
  data_type = data_type,
  cohort_a_sample_count = cohort_a_sample_count,
  cohort_b_sample_count = cohort_b_sample_count,
  patient_count = length(unique(samples$patient_id)),
  feature_count = nrow(result),
  observed_feature_count = nrow(result),
  tested_feature_count = nrow(tested_result),
  skipped_feature_count = nrow(result) - nrow(tested_result),
  significant_feature_count = significant_feature_count,
  insufficient_complete_case_feature_count = sum(result$status == "insufficient_complete_cases"),
  constant_feature_count = sum(result$status == "constant"),
  top_feature = if (is.null(top)) "" else top$feature_id[[1]],
  top_rank_biserial_effect = if (is.null(top)) NULL else top$rank_biserial_effect[[1]],
  top_adj_p_value = if (is.null(top)) NULL else top$adj_p_value[[1]],
  adjustment_status = "unadjusted_exploratory",
  contrast = "Cohort A - Cohort B",
  method = "two-sided Wilcoxon rank-sum test with Benjamini-Hochberg correction",
  effect_size_method = "rank-biserial correlation: 2U/(nA*nB)-1",
  data_scale = "supplied assay scale",
  missing_value_handling = "feature-wise complete cases; at least three observations per cohort required",
  supplied_scale = TRUE,
  source_matrix_materialized_in_duckdb = FALSE,
  source_matrix_copied_to_job = FALSE,
  caveats = caveats,
  r_version = R.version.string,
  results = result
)
write_json_file(summary_path, summary)

reply <- paste0(
  "Exploratory ", ifelse(nzchar(data_type), data_type, modality), " comparison completed for ",
  dataset_name, ". Tested ", nrow(tested_result), " of ", nrow(result), " features across ",
  cohort_a_sample_count, " Cohort A and ", cohort_b_sample_count, " Cohort B samples; ",
  significant_feature_count, " passed BH < 0.05. ",
  if (is.null(top)) {
    "No feature met the minimum complete-case and variability requirements. "
  } else {
    paste0(
      "The top-ranked feature was ", top$feature_id[[1]], " (rank-biserial effect ",
      formatC(top$rank_biserial_effect[[1]], format = "f", digits = 3), ", BH q ",
      formatC(top$adj_p_value[[1]], format = "g", digits = 3), "). "
    )
  },
  "Wilcoxon rank-sum tests used feature-wise complete cases on the supplied scale. ",
  "This comparison is unadjusted and exploratory; no covariates were modeled."
)

context <- c(
  list(
    mode = "external_rscript_quantitative_assay_wilcoxon_comparison",
    runner = "quantitative_assay_wilcoxon_comparison",
    prompt_supplied = nzchar(prompt)
  ),
  summary
)
cat(jsonlite::toJSON(
  list(reply = reply, context = context),
  auto_unbox = TRUE,
  null = "null",
  na = "null",
  digits = 10
))
