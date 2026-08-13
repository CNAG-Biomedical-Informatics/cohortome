script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)[1]
script_path <- sub("^--file=", "", script_argument)
source(file.path(dirname(normalizePath(script_path)), "analysis_r_methylation_common.R"))

if (!requireNamespace("limma", quietly = TRUE)) {
  stop("limma is required for differential methylation.")
}
if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("jsonlite is required for differential methylation.")
}
suppressPackageStartupMessages(library(limma))

prompt <- arg_value("--prompt", "")
dataset_name <- arg_value("--dataset-name", "")
matrix_path <- arg_value("--matrix", "")
sample_table_path <- arg_value("--sample-table", "")
covariates_path <- arg_value("--covariates-file", "")
results_path <- arg_value("--results-table", "")
volcano_path <- arg_value("--volcano-table", "")
summary_path <- arg_value("--summary-json", "")
plot_path <- arg_value("--plot-file", "")

samples <- prepare_sample_table(sample_table_path, require_compare = TRUE)
covariate_specs <- read_covariate_specs(covariates_path)
covariates <- covariate_specs$name
covariate_types <- setNames(covariate_specs$type, covariate_specs$name)
adjustment_status <- if (length(covariates)) "covariate_adjusted" else "unadjusted_exploratory"
missing_covariates <- setdiff(covariates, names(samples))
if (length(missing_covariates)) {
  stop("The scoped sample table is missing declared methylation covariates.")
}

design_data <- data.frame(cohort = factor(samples$cohort, levels = c("B", "A")))
safe_covariate_names <- make.names(covariates, unique = TRUE)
for (index in seq_along(covariates)) {
  covariate <- covariates[[index]]
  values <- trimws(as.character(samples[[covariate]]))
  if (any(!nzchar(values))) {
    stop("Differential methylation requires complete values for every declared covariate.")
  }
  design_data[[safe_covariate_names[[index]]]] <- if (covariate_types[[covariate]] == "numeric") {
    numeric_values <- suppressWarnings(as.numeric(values))
    if (any(!is.finite(numeric_values))) {
      stop("A numeric methylation analysis covariate contains a non-numeric value.")
    }
    numeric_values
  } else {
    factor(values)
  }
}

design <- model.matrix(reformulate(c("cohort", safe_covariate_names)), data = design_data)
coefficient <- "cohortA"
if (!coefficient %in% colnames(design)) {
  stop("Unable to resolve the Cohort A versus Cohort B coefficient.")
}
design_rank <- qr(design)$rank
if (design_rank < ncol(design)) {
  stop("The methylation design is rank deficient; cohort and declared covariates cannot be estimated independently.")
}
residual_degrees_of_freedom <- nrow(design) - design_rank
if (residual_degrees_of_freedom < 1L) {
  stop("The methylation design has no residual degrees of freedom.")
}

fit_chunks <- list()
chunk_index <- 0L
observed_feature_count <- 0L
analyzed_feature_count <- 0L
missing_filtered_feature_count <- 0L
constant_filtered_feature_count <- 0L

invisible(stream_methylation_matrix(
  matrix_path,
  samples$sample_id,
  callback = function(frame) {
    values <- as.matrix(frame[, -1, drop = FALSE])
    storage.mode(values) <- "numeric"
    if (any(is.infinite(values))) {
      stop("Methylation M-values must be finite or missing.")
    }
    feature_ids <- as.character(frame$feature_id)
    observed_feature_count <<- observed_feature_count + nrow(values)
    complete <- rowSums(is.finite(values)) == ncol(values)
    row_sums <- rowSums(values, na.rm = TRUE)
    row_sums_squares <- rowSums(values ^ 2, na.rm = TRUE)
    centered_sums_squares <- row_sums_squares - (row_sums ^ 2) / ncol(values)
    variable <- complete & is.finite(centered_sums_squares) & centered_sums_squares > 0
    missing_filtered_feature_count <<- missing_filtered_feature_count + sum(!complete)
    constant_filtered_feature_count <<- constant_filtered_feature_count + sum(complete & !variable)
    if (!any(variable)) {
      return(invisible(NULL))
    }
    selected_values <- values[variable, , drop = FALSE]
    rownames(selected_values) <- feature_ids[variable]
    chunk_index <<- chunk_index + 1L
    fit_chunks[[chunk_index]] <<- limma::lmFit(selected_values, design)
    analyzed_feature_count <<- analyzed_feature_count + nrow(selected_values)
    invisible(NULL)
  }
))

if (analyzed_feature_count < 2L || !length(fit_chunks)) {
  stop("Too few complete, variable CpG probes remain for differential methylation.")
}

fit <- fit_chunks[[1]]
fit$coefficients <- do.call(rbind, lapply(fit_chunks, function(value) value$coefficients))
fit$stdev.unscaled <- do.call(rbind, lapply(fit_chunks, function(value) value$stdev.unscaled))
fit$sigma <- unlist(lapply(fit_chunks, function(value) value$sigma), use.names = TRUE)
fit$df.residual <- unlist(lapply(fit_chunks, function(value) value$df.residual), use.names = TRUE)
fit$Amean <- unlist(lapply(fit_chunks, function(value) value$Amean), use.names = TRUE)
if (anyDuplicated(rownames(fit$coefficients))) {
  stop("The methylation matrix contains duplicate CpG identifiers.")
}
fit_chunks <- NULL
invisible(gc())

fit <- limma::eBayes(fit)
table <- limma::topTable(fit, coef = coefficient, number = Inf, sort.by = "none")
result <- data.frame(
  cpg_id = rownames(table),
  mean_m_value = table$AveExpr,
  m_value_difference = table$logFC,
  t = table$t,
  p_value = table$P.Value,
  adj_p_value = table$adj.P.Val,
  b_statistic = table$B,
  stringsAsFactors = FALSE
)
result$p_value[!is.finite(result$p_value)] <- 1
result$adj_p_value[!is.finite(result$adj_p_value)] <- 1
result$neg_log10_p <- -log10(pmax(result$p_value, 1e-300))
result <- result[order(result$adj_p_value, -abs(result$m_value_difference), result$cpg_id), , drop = FALSE]
write.table(result, results_path, sep = "\t", row.names = FALSE, quote = FALSE)

volcano_point_limit <- 50000L
volcano_indices <- bounded_ranked_indices(nrow(result), volcano_point_limit)
volcano <- result[volcano_indices, c("cpg_id", "m_value_difference", "p_value", "adj_p_value", "neg_log10_p"), drop = FALSE]
write.table(
  volcano,
  volcano_path,
  sep = "\t",
  row.names = FALSE,
  quote = FALSE
)

significant <- result$adj_p_value < 0.05
significant_count <- sum(significant, na.rm = TRUE)
hypermethylated_count <- sum(significant & result$m_value_difference > 0, na.rm = TRUE)
hypomethylated_count <- sum(significant & result$m_value_difference < 0, na.rm = TRUE)
top <- if (nrow(result)) result[1, , drop = FALSE] else NULL

png(plot_path, width = 960, height = 720)
plot(
  volcano$m_value_difference,
  volcano$neg_log10_p,
  pch = 16,
  col = ifelse(volcano$adj_p_value < 0.05, "#d9485f", "#94a3b8"),
  xlab = "M-value difference (Cohort A - Cohort B)",
  ylab = "-log10 p-value",
  main = sprintf("Differential methylation: %s", dataset_name)
)
abline(v = 0, col = "#475569", lty = 2)
if (nrow(result)) {
  top_count <- min(5L, nrow(result))
  text(
    result$m_value_difference[seq_len(top_count)],
    result$neg_log10_p[seq_len(top_count)],
    labels = result$cpg_id[seq_len(top_count)],
    pos = 3,
    cex = 0.8,
    col = "#111827"
  )
}
invisible(dev.off())

summary <- list(
  dataset_name = dataset_name,
  cohort_a_sample_count = sum(samples$cohort == "A"),
  cohort_b_sample_count = sum(samples$cohort == "B"),
  patient_count = length(unique(samples$patient_id)),
  observed_feature_count = observed_feature_count,
  analyzed_feature_count = analyzed_feature_count,
  missing_filtered_feature_count = missing_filtered_feature_count,
  constant_filtered_feature_count = constant_filtered_feature_count,
  plotted_point_count = nrow(volcano),
  volcano_point_limit = volcano_point_limit,
  plotted_significant_cpg_count = sum(volcano$adj_p_value < 0.05, na.rm = TRUE),
  significant_cpg_count = significant_count,
  hypermethylated_cpg_count = hypermethylated_count,
  hypomethylated_cpg_count = hypomethylated_count,
  top_cpg = if (is.null(top)) "" else top$cpg_id[[1]],
  top_m_value_difference = if (is.null(top)) NULL else top$m_value_difference[[1]],
  top_adj_p_value = if (is.null(top)) NULL else top$adj_p_value[[1]],
  covariates_used = unname(covariates),
  analysis_covariate_types = as.list(covariate_types),
  adjustment_status = adjustment_status,
  design_columns = unname(colnames(design)),
  design_rank = design_rank,
  residual_degrees_of_freedom = residual_degrees_of_freedom,
  contrast = "Cohort A - Cohort B",
  method = "limma on supplied M-values",
  missing_value_handling = "exclude probes with any missing selected-sample value",
  source_matrix_materialized_in_duckdb = FALSE,
  r_version = R.version.string,
  limma_version = as.character(utils::packageVersion("limma"))
)
write_json_file(summary_path, summary)

reply <- paste0(
  "Differential methylation completed for ", dataset_name, ". Analyzed ", analyzed_feature_count,
  " CpG probes across ", sum(samples$cohort == "A"), " Cohort A and ",
  sum(samples$cohort == "B"), " Cohort B samples; ", significant_count,
  " passed BH < 0.05. ",
  if (adjustment_status == "covariate_adjusted") {
    paste0("The model adjusted for ", length(covariates), " declared covariate(s).")
  } else {
    "This comparison is unadjusted and exploratory."
  }
)
context <- c(
  list(
    mode = "external_rscript_methylation_limma_differential_methylation",
    runner = "methylation_limma_differential_methylation",
    prompt = prompt
  ),
  summary
)
emit_result(reply, context)
