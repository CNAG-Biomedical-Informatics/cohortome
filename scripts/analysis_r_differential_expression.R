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

read_tsv <- function(path) {
  if (!nzchar(path) || !file.exists(path)) {
    stop(sprintf("Required input file is missing: %s", path))
  }
  read.delim(path, sep = "\t", header = TRUE, stringsAsFactors = FALSE, check.names = FALSE)
}

safe_numeric_matrix <- function(frame) {
  if (ncol(frame) < 2) {
    stop("Counts matrix must contain at least one sample column.")
  }
  values <- as.matrix(frame[, -1, drop = FALSE])
  storage.mode(values) <- "numeric"
  rownames(values) <- frame[[1]]
  values
}

prompt <- read_arg("--prompt", "")
dataset_name <- read_arg("--dataset-name", "")
sample_table_path <- read_arg("--sample-table", "")
counts_matrix_path <- read_arg("--counts-matrix", "")
results_table_path <- read_arg("--results-table", "")
volcano_table_path <- read_arg("--volcano-table", "")
summary_json_path <- read_arg("--summary-json", "")
plot_file_path <- read_arg("--plot-file", "")

sample_table <- read_tsv(sample_table_path)
counts_frame <- read_tsv(counts_matrix_path)
counts_matrix <- safe_numeric_matrix(counts_frame)

if (!"sample_id" %in% names(sample_table) || !"cohort" %in% names(sample_table)) {
  stop("Sample table must contain sample_id and cohort columns.")
}

sample_ids <- colnames(counts_matrix)
sample_table <- sample_table[match(sample_ids, sample_table$sample_id), , drop = FALSE]
if (any(is.na(sample_table$sample_id))) {
  stop("Counts matrix columns do not align with the sample table.")
}

cohort_a_index <- which(sample_table$cohort == "A")
cohort_b_index <- which(sample_table$cohort == "B")
if (length(cohort_a_index) < 1 || length(cohort_b_index) < 1) {
  stop("Differential expression requires at least one sample in Cohort A and Cohort B.")
}

library_sizes <- pmax(colSums(counts_matrix), 1)
log2_cpm <- log2(t(t(counts_matrix) / library_sizes) * 1e6 + 1)

gene_ids <- rownames(log2_cpm)
result_rows <- vector("list", length(gene_ids))
for (index in seq_along(gene_ids)) {
  gene_id <- gene_ids[[index]]
  values_a <- as.numeric(log2_cpm[index, cohort_a_index])
  values_b <- as.numeric(log2_cpm[index, cohort_b_index])
  mean_a <- mean(values_a)
  mean_b <- mean(values_b)
  log2_fc <- mean_a - mean_b
  p_value <- 1.0
  if (length(values_a) >= 2 && length(values_b) >= 2) {
    test_result <- tryCatch(t.test(values_a, values_b), error = function(e) NULL)
    if (!is.null(test_result) && !is.null(test_result$p.value) && is.finite(test_result$p.value)) {
      p_value <- max(as.numeric(test_result$p.value), 1e-300)
    }
  }
  result_rows[[index]] <- data.frame(
    gene_id = gene_id,
    mean_log2_cpm_a = round(mean_a, 6),
    mean_log2_cpm_b = round(mean_b, 6),
    log2_fold_change = round(log2_fc, 6),
    p_value = p_value,
    sample_count_a = length(values_a),
    sample_count_b = length(values_b),
    stringsAsFactors = FALSE
  )
}

results <- do.call(rbind, result_rows)
results$adj_p_value <- p.adjust(results$p_value, method = "BH")
results$neg_log10_p <- -log10(pmax(results$p_value, 1e-300))
results <- results[order(results$adj_p_value, -abs(results$log2_fold_change), results$gene_id), , drop = FALSE]
write.table(results, file = results_table_path, sep = "\t", row.names = FALSE, quote = FALSE)

volcano <- results[, c("gene_id", "log2_fold_change", "p_value", "adj_p_value", "neg_log10_p"), drop = FALSE]
write.table(volcano, file = volcano_table_path, sep = "\t", row.names = FALSE, quote = FALSE)

significant <- results[results$adj_p_value < 0.05, , drop = FALSE]
top_hits <- head(results, 10)
top_gene <- if (nrow(top_hits) >= 1) as.character(top_hits$gene_id[[1]]) else "n/a"
top_log2_fc <- if (nrow(top_hits) >= 1) round(as.numeric(top_hits$log2_fold_change[[1]]), 3) else 0
top_adj_p <- if (nrow(top_hits) >= 1) signif(as.numeric(top_hits$adj_p_value[[1]]), 3) else 1

png(filename = plot_file_path, width = 960, height = 720)
plot(
  volcano$log2_fold_change,
  volcano$neg_log10_p,
  pch = 16,
  col = ifelse(volcano$adj_p_value < 0.05, "#d9485f", "#94a3b8"),
  xlab = "log2 fold change (Cohort A - Cohort B)",
  ylab = "-log10 p-value",
  main = sprintf("Differential expression: %s", dataset_name)
)
abline(v = 0, col = "#475569", lty = 2)
if (nrow(top_hits) >= 1) {
  text(
    top_hits$log2_fold_change[seq_len(min(5, nrow(top_hits)))],
    top_hits$neg_log10_p[seq_len(min(5, nrow(top_hits)))],
    labels = top_hits$gene_id[seq_len(min(5, nrow(top_hits)))],
    pos = 3,
    cex = 0.8,
    col = "#111827"
  )
}
invisible(dev.off())

summary_json <- paste0(
  "{",
  "\"dataset_name\":", json_quote(dataset_name), ",",
  "\"cohort_a_sample_count\":", length(cohort_a_index), ",",
  "\"cohort_b_sample_count\":", length(cohort_b_index), ",",
  "\"gene_count\":", nrow(results), ",",
  "\"significant_gene_count\":", nrow(significant), ",",
  "\"top_gene\":", json_quote(top_gene), ",",
  "\"top_log2_fold_change\":", top_log2_fc, ",",
  "\"top_adj_p_value\":", top_adj_p,
  "}"
)
writeLines(summary_json, con = summary_json_path, useBytes = TRUE)

reply_lines <- c(
  "### External R differential expression",
  "",
  sprintf("- Dataset: %s", dataset_name),
  sprintf("- Cohort A samples: %d", length(cohort_a_index)),
  sprintf("- Cohort B samples: %d", length(cohort_b_index)),
  sprintf("- Genes tested: %d", nrow(results)),
  sprintf("- Significant genes (BH < 0.05): %d", nrow(significant)),
  sprintf("- Top hit: %s (log2FC %.3f, adjusted p-value %s)", top_gene, top_log2_fc, format(top_adj_p, scientific = TRUE)),
  "",
  "This result was produced by a curated external Rscript from a job-scoped molecular differential-expression bundle."
)
reply <- paste(reply_lines, collapse = "\n")

json <- paste0(
  "{",
  "\"reply\":", json_quote(reply), ",",
  "\"context\":{",
  "\"mode\":\"external_rscript_molecular_differential_expression\",",
  "\"runner\":\"molecular_differential_expression\",",
  "\"prompt\":", json_quote(prompt), ",",
  "\"dataset_name\":", json_quote(dataset_name), ",",
  "\"cohort_a_sample_count\":", length(cohort_a_index), ",",
  "\"cohort_b_sample_count\":", length(cohort_b_index), ",",
  "\"gene_count\":", nrow(results), ",",
  "\"significant_gene_count\":", nrow(significant), ",",
  "\"top_gene\":", json_quote(top_gene), ",",
  "\"top_log2_fold_change\":", top_log2_fc, ",",
  "\"top_adj_p_value\":", top_adj_p,
  "}",
  "}"
)

cat(json)
