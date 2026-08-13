script_argument <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)[1]
script_path <- sub("^--file=", "", script_argument)
source(file.path(dirname(normalizePath(script_path)), "analysis_r_methylation_common.R"))

if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("jsonlite is required for methylation QC and PCA.")
}

prompt <- arg_value("--prompt", "")
dataset_name <- arg_value("--dataset-name", "")
matrix_path <- arg_value("--matrix", "")
sample_table_path <- arg_value("--sample-table", "")
covariates_path <- arg_value("--covariates-file", "")
feature_limit <- suppressWarnings(as.integer(arg_value("--feature-limit", "5000")))
sample_qc_path <- arg_value("--sample-qc", "")
pca_scores_path <- arg_value("--pca-scores", "")
pca_variance_path <- arg_value("--pca-variance", "")
associations_path <- arg_value("--covariate-associations", "")
summary_path <- arg_value("--summary-json", "")
plot_path <- arg_value("--plot-file", "")

samples <- prepare_sample_table(sample_table_path, require_compare = FALSE)
if (nrow(samples) < 2L) {
  stop("Methylation QC and PCA requires at least two samples.")
}
if (!is.finite(feature_limit) || feature_limit < 100L || feature_limit > 50000L) {
  stop("Methylation PCA feature limit must be between 100 and 50000.")
}
covariate_specs <- read_covariate_specs(covariates_path)
covariates <- covariate_specs$name
covariate_types <- setNames(covariate_specs$type, covariate_specs$name)
missing_covariates <- setdiff(covariates, names(samples))
if (length(missing_covariates)) {
  stop("The scoped sample table is missing declared methylation covariates.")
}

sample_count <- nrow(samples)
value_count <- numeric(sample_count)
missing_count <- numeric(sample_count)
value_sum <- numeric(sample_count)
value_sum_squares <- numeric(sample_count)
value_min <- rep(Inf, sample_count)
value_max <- rep(-Inf, sample_count)
top_feature_ids <- character()
top_feature_variances <- numeric()
top_centered_values <- matrix(numeric(), nrow = 0L, ncol = sample_count)
variable_feature_count <- 0L

observed_feature_count <- stream_methylation_matrix(
  matrix_path,
  samples$sample_id,
  callback = function(frame) {
    values <- as.matrix(frame[, -1, drop = FALSE])
    storage.mode(values) <- "numeric"
    if (any(is.infinite(values))) {
      stop("Methylation M-values must be finite or missing.")
    }
    finite <- is.finite(values)
    safe_values <- values
    safe_values[!finite] <- 0
    value_count <<- value_count + colSums(finite)
    missing_count <<- missing_count + colSums(!finite)
    value_sum <<- value_sum + colSums(safe_values)
    value_sum_squares <<- value_sum_squares + colSums(safe_values ^ 2)
    for (column in seq_len(ncol(values))) {
      observed <- values[finite[, column], column]
      if (length(observed)) {
        value_min[[column]] <<- min(value_min[[column]], min(observed))
        value_max[[column]] <<- max(value_max[[column]], max(observed))
      }
    }

    row_counts <- rowSums(finite)
    row_means <- rowSums(safe_values) / pmax(row_counts, 1)
    centered <- sweep(values, 1L, row_means, FUN = "-")
    centered[!finite] <- 0
    row_sums_squares <- rowSums(centered ^ 2)
    keep <- row_counts >= 2L & is.finite(row_sums_squares) & row_sums_squares > 0
    if (any(keep)) {
      candidate_values <- rbind(top_centered_values, centered[keep, , drop = FALSE])
      candidate_ids <- c(top_feature_ids, as.character(frame$feature_id[keep]))
      candidate_variances <- c(
        top_feature_variances,
        row_sums_squares[keep] / pmax(row_counts[keep] - 1L, 1L)
      )
      retain <- order(candidate_variances, decreasing = TRUE, na.last = NA)
      retain <- retain[seq_len(min(length(retain), feature_limit))]
      top_centered_values <<- candidate_values[retain, , drop = FALSE]
      top_feature_ids <<- candidate_ids[retain]
      top_feature_variances <<- candidate_variances[retain]
      variable_feature_count <<- variable_feature_count + sum(keep)
    }
  }
)

if (observed_feature_count < 2L || variable_feature_count < 2L) {
  stop("Too few variable CpG probes remain for methylation PCA.")
}
if (any(value_count == 0)) {
  stop("At least one selected methylation sample has no finite M-values.")
}

sample_gram <- crossprod(top_centered_values)
eigen_result <- eigen(sample_gram, symmetric = TRUE)
positive <- which(eigen_result$values > max(eigen_result$values, 0) * 1e-12)
component_count <- min(10L, length(positive), sample_count - 1L)
if (component_count < 1L) {
  stop("Methylation PCA did not produce a positive component.")
}
component_indices <- positive[seq_len(component_count)]
component_values <- pmax(eigen_result$values[component_indices], 0)
scores <- sweep(
  eigen_result$vectors[, component_indices, drop = FALSE],
  2L,
  sqrt(component_values),
  FUN = "*"
)
colnames(scores) <- paste0("PC", seq_len(component_count))
total_positive_variance <- sum(pmax(eigen_result$values, 0))
variance_fraction <- if (total_positive_variance > 0) component_values / total_positive_variance else rep(0, component_count)

sample_means <- value_sum / value_count
sample_variances <- pmax((value_sum_squares - (value_sum ^ 2) / value_count) / pmax(value_count - 1, 1), 0)
sample_qc <- data.frame(
  sample_id = samples$sample_id,
  patient_id = samples$patient_id,
  cohort = samples$cohort,
  observed_value_count = as.integer(value_count),
  missing_value_count = as.integer(missing_count),
  missing_fraction = missing_count / pmax(value_count + missing_count, 1),
  mean_m_value = sample_means,
  sd_m_value = sqrt(sample_variances),
  minimum_m_value = ifelse(is.finite(value_min), value_min, NA_real_),
  maximum_m_value = ifelse(is.finite(value_max), value_max, NA_real_),
  stringsAsFactors = FALSE
)
write.table(sample_qc, sample_qc_path, sep = "\t", row.names = FALSE, quote = FALSE, na = "")

score_frame <- data.frame(
  sample_id = samples$sample_id,
  patient_id = samples$patient_id,
  cohort = samples$cohort,
  scores,
  check.names = FALSE,
  stringsAsFactors = FALSE
)
write.table(score_frame, pca_scores_path, sep = "\t", row.names = FALSE, quote = FALSE, na = "")
variance_frame <- data.frame(
  component = paste0("PC", seq_len(component_count)),
  eigenvalue = component_values,
  variance_fraction = variance_fraction,
  stringsAsFactors = FALSE
)
write.table(variance_frame, pca_variance_path, sep = "\t", row.names = FALSE, quote = FALSE)

association_rows <- list()
association_index <- 0L
for (covariate in covariates) {
  raw_values <- trimws(as.character(samples[[covariate]]))
  for (component in seq_len(min(5L, component_count))) {
    component_scores <- scores[, component]
    if (covariate_types[[covariate]] == "numeric") {
      numeric_values <- suppressWarnings(as.numeric(raw_values))
      keep <- nzchar(raw_values) & is.finite(numeric_values) & is.finite(component_scores)
      if (sum(keep) < 3L || length(unique(numeric_values[keep])) < 2L) {
        next
      }
      test <- suppressWarnings(cor.test(component_scores[keep], numeric_values[keep], method = "pearson"))
      effect <- unname(test$estimate)
      p_value <- test$p.value
      method <- "pearson_correlation"
    } else {
      keep <- nzchar(raw_values) & is.finite(component_scores)
      groups <- factor(raw_values[keep])
      if (sum(keep) < 3L || nlevels(groups) < 2L || nlevels(groups) >= sum(keep)) {
        next
      }
      model <- lm(component_scores[keep] ~ groups)
      model_anova <- anova(model)
      p_value <- model_anova[["Pr(>F)"]][[1]]
      group_means <- tapply(component_scores[keep], groups, mean)
      effect <- max(group_means) - min(group_means)
      method <- "one_way_anova"
    }
    association_index <- association_index + 1L
    association_rows[[association_index]] <- data.frame(
      covariate = covariate,
      component = paste0("PC", component),
      method = method,
      effect = effect,
      p_value = p_value,
      stringsAsFactors = FALSE
    )
  }
}
associations <- if (length(association_rows)) {
  do.call(rbind, association_rows)
} else {
  data.frame(
    covariate = character(),
    component = character(),
    method = character(),
    effect = numeric(),
    p_value = numeric(),
    adj_p_value = numeric(),
    stringsAsFactors = FALSE
  )
}
if (nrow(associations)) {
  associations$adj_p_value <- p.adjust(associations$p_value, method = "BH")
  associations <- associations[order(
    associations$adj_p_value,
    associations$p_value,
    associations$covariate,
    associations$component
  ), , drop = FALSE]
}
write.table(associations, associations_path, sep = "\t", row.names = FALSE, quote = FALSE)

plot_groups <- as.character(samples$cohort)
plot_group_label <- "scope"
if (length(unique(plot_groups)) < 2L && length(covariates)) {
  candidate <- trimws(as.character(samples[[covariates[[1]]]]))
  if (length(unique(candidate[nzchar(candidate)])) >= 2L) {
    plot_groups <- candidate
    plot_group_label <- covariates[[1]]
  }
}
plot_factor <- factor(plot_groups)
colors <- grDevices::hcl.colors(max(3L, nlevels(plot_factor)), palette = "Dark 3")[as.integer(plot_factor)]
pc2 <- if (component_count >= 2L) scores[, 2] else rep(0, sample_count)
pc2_variance <- if (component_count >= 2L) variance_fraction[[2]] else 0
png(plot_path, width = 960, height = 720)
plot(
  scores[, 1],
  pc2,
  pch = 16,
  col = colors,
  xlab = sprintf("PC1 (%.1f%%)", 100 * variance_fraction[[1]]),
  ylab = sprintf("PC2 (%.1f%%)", 100 * pc2_variance),
  main = sprintf("Methylation PCA: %s", dataset_name)
)
if (nlevels(plot_factor) > 1L && nlevels(plot_factor) <= 12L) {
  legend(
    "topright",
    legend = levels(plot_factor),
    col = grDevices::hcl.colors(max(3L, nlevels(plot_factor)), palette = "Dark 3")[seq_len(nlevels(plot_factor))],
    pch = 16,
    title = plot_group_label,
    cex = 0.8
  )
}
invisible(dev.off())

total_cells <- sum(value_count + missing_count)
total_missing <- sum(missing_count)
strongest_association <- if (nrow(associations)) associations[1, , drop = FALSE] else NULL
summary <- list(
  dataset_name = dataset_name,
  sample_count = sample_count,
  patient_count = length(unique(samples$patient_id)),
  observed_feature_count = observed_feature_count,
  variable_feature_count = variable_feature_count,
  pca_feature_count = nrow(top_centered_values),
  pca_feature_limit = feature_limit,
  missing_value_count = as.integer(total_missing),
  missing_fraction = if (total_cells > 0) total_missing / total_cells else 0,
  pca_component_count = component_count,
  pc1_variance_fraction = variance_fraction[[1]],
  pc2_variance_fraction = pc2_variance,
  covariates_used = unname(covariates),
  analysis_covariate_types = as.list(covariate_types),
  strongest_covariate = if (is.null(strongest_association)) "" else strongest_association$covariate[[1]],
  strongest_covariate_component = if (is.null(strongest_association)) "" else strongest_association$component[[1]],
  strongest_covariate_p_value = if (is.null(strongest_association)) NULL else strongest_association$p_value[[1]],
  strongest_covariate_adj_p_value = if (is.null(strongest_association)) NULL else strongest_association$adj_p_value[[1]],
  association_scope = "exploratory_one_covariate_at_a_time_bh_adjusted",
  method = "streaming top-variable-CpG sample-Gram PCA on supplied M-values",
  missing_value_handling = "probe mean for PCA; explicit counts retained in sample QC",
  source_matrix_materialized_in_duckdb = FALSE,
  r_version = R.version.string
)
write_json_file(summary_path, summary)

reply <- paste0(
  "Methylation QC and PCA completed for ", dataset_name, ". Processed ",
  observed_feature_count, " CpG probes across ", sample_count, " scoped samples and used the ",
  nrow(top_centered_values), " most variable probes for PCA; PC1 explained ",
  sprintf("%.1f", 100 * variance_fraction[[1]]), "% of observed variance."
)
context <- c(
  list(
    mode = "external_rscript_methylation_qc_pca",
    runner = "methylation_qc_pca",
    prompt = prompt
  ),
  summary
)
emit_result(reply, context)
