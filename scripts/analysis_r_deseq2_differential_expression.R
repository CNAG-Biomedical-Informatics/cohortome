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

safe_count_matrix <- function(frame) {
  if (ncol(frame) < 2) {
    stop("Counts matrix must contain at least one sample column.")
  }
  values <- as.matrix(frame[, -1, drop = FALSE])
  storage.mode(values) <- "numeric"
  values <- round(values)
  if (any(is.na(values)) || any(values < 0)) {
    stop("DESeq2 requires a non-negative integer count matrix.")
  }
  rownames(values) <- frame[[1]]
  values
}

if (!requireNamespace("DESeq2", quietly = TRUE)) {
  stop("DESeq2 is not installed in the configured R library.")
}
if (!requireNamespace("apeglm", quietly = TRUE)) {
  stop("apeglm is not installed in the configured R library.")
}

suppressPackageStartupMessages(library(DESeq2))

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
counts_matrix <- safe_count_matrix(counts_frame)

required_cols <- c("sample_id", "patient_id", "cohort")
if (!all(required_cols %in% names(sample_table))) {
  stop("Sample table must contain sample_id, patient_id, and cohort columns.")
}

sample_ids <- colnames(counts_matrix)
sample_table <- sample_table[match(sample_ids, sample_table$sample_id), , drop = FALSE]
if (any(is.na(sample_table$sample_id))) {
  stop("Counts matrix columns do not align with the sample table.")
}

sample_table$patient_id <- as.character(sample_table$patient_id)
sample_table$cohort <- as.character(sample_table$cohort)

if (anyDuplicated(sample_table$patient_id)) {
  stop("DESeq2 differential expression v1 requires one sample per patient.")
}

cohort_a_index <- which(sample_table$cohort == "A")
cohort_b_index <- which(sample_table$cohort == "B")
if (length(cohort_a_index) < 2 || length(cohort_b_index) < 2) {
  stop("DESeq2 differential expression requires at least two samples in Cohort A and two samples in Cohort B.")
}

keep_genes <- rowSums(counts_matrix >= 10) >= 2
filtered_counts <- counts_matrix[keep_genes, , drop = FALSE]
if (nrow(filtered_counts) < 2) {
  stop("Too few genes remain after minimal count filtering for DESeq2.")
}

sample_table$condition <- factor(sample_table$cohort, levels = c("B", "A"))
rownames(sample_table) <- sample_table$sample_id

dds <- DESeqDataSetFromMatrix(
  countData = filtered_counts,
  colData = sample_table,
  design = ~ condition
)
dds <- DESeq(dds, quiet = TRUE)

coef_name <- grep("^condition_", resultsNames(dds), value = TRUE)[1]
if (!nzchar(coef_name)) {
  stop("Unable to resolve a DESeq2 condition coefficient.")
}

res <- results(dds, name = coef_name, independentFiltering = TRUE, alpha = 0.05)
res_shrunk <- lfcShrink(dds, coef = coef_name, type = "apeglm", quiet = TRUE)

result_df <- data.frame(
  gene_id = rownames(res),
  base_mean = res$baseMean,
  log2_fold_change = res_shrunk$log2FoldChange,
  lfc_se = res_shrunk$lfcSE,
  stat = res$stat,
  p_value = res$pvalue,
  adj_p_value = res$padj,
  stringsAsFactors = FALSE
)

result_df$p_value[is.na(result_df$p_value)] <- 1
result_df$adj_p_value[is.na(result_df$adj_p_value)] <- 1
result_df$neg_log10_p <- -log10(pmax(result_df$p_value, 1e-300))
result_df <- result_df[order(result_df$adj_p_value, -abs(result_df$log2_fold_change), result_df$gene_id), , drop = FALSE]

write.table(result_df, file = results_table_path, sep = "\t", row.names = FALSE, quote = FALSE)

volcano <- result_df[, c("gene_id", "log2_fold_change", "p_value", "adj_p_value", "neg_log10_p"), drop = FALSE]
write.table(volcano, file = volcano_table_path, sep = "\t", row.names = FALSE, quote = FALSE)

significant <- result_df[result_df$adj_p_value < 0.05, , drop = FALSE]
top_hits <- head(result_df, 10)
top_gene <- if (nrow(top_hits) >= 1) as.character(top_hits$gene_id[[1]]) else "n/a"
top_log2_fc <- if (nrow(top_hits) >= 1) round(as.numeric(top_hits$log2_fold_change[[1]]), 3) else 0
top_adj_p <- if (nrow(top_hits) >= 1) signif(as.numeric(top_hits$adj_p_value[[1]]), 3) else 1

png(filename = plot_file_path, width = 960, height = 720)
plot(
  volcano$log2_fold_change,
  volcano$neg_log10_p,
  pch = 16,
  col = ifelse(volcano$adj_p_value < 0.05, "#d9485f", "#94a3b8"),
  xlab = "shrunken log2 fold change (Cohort A - Cohort B)",
  ylab = "-log10 p-value",
  main = sprintf("DESeq2 differential expression: %s", dataset_name)
)
abline(v = 0, col = "#475569", lty = 2)
if (nrow(top_hits) >= 1) {
  top_n <- min(5, nrow(top_hits))
  text(
    top_hits$log2_fold_change[seq_len(top_n)],
    top_hits$neg_log10_p[seq_len(top_n)],
    labels = top_hits$gene_id[seq_len(top_n)],
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
  "\"tested_gene_count\":", nrow(counts_matrix), ",",
  "\"filtered_gene_count\":", nrow(filtered_counts), ",",
  "\"significant_gene_count\":", nrow(significant), ",",
  "\"top_gene\":", json_quote(top_gene), ",",
  "\"top_log2_fold_change\":", top_log2_fc, ",",
  "\"top_adj_p_value\":", top_adj_p, ",",
  "\"shrinkage_method\":\"apeglm\"",
  "}"
)
writeLines(summary_json, con = summary_json_path, useBytes = TRUE)

reply_lines <- c(
  "### External R DESeq2 differential expression",
  "",
  sprintf("- Dataset: %s", dataset_name),
  sprintf("- Cohort A samples: %d", length(cohort_a_index)),
  sprintf("- Cohort B samples: %d", length(cohort_b_index)),
  sprintf("- Genes tested: %d", nrow(counts_matrix)),
  sprintf("- Genes kept after count filtering: %d", nrow(filtered_counts)),
  sprintf("- Significant genes (BH < 0.05): %d", nrow(significant)),
  sprintf("- Top hit: %s (shrunken log2FC %.3f, adjusted p-value %s)", top_gene, top_log2_fc, format(top_adj_p, scientific = TRUE)),
  "",
  "This result was produced by a curated external Rscript using DESeq2 with apeglm shrinkage."
)
reply <- paste(reply_lines, collapse = "\n")

json <- paste0(
  "{",
  "\"reply\":", json_quote(reply), ",",
  "\"context\":{",
  "\"mode\":\"external_rscript_molecular_deseq2_differential_expression\",",
  "\"runner\":\"molecular_deseq2_differential_expression\",",
  "\"prompt\":", json_quote(prompt), ",",
  "\"dataset_name\":", json_quote(dataset_name), ",",
  "\"cohort_a_sample_count\":", length(cohort_a_index), ",",
  "\"cohort_b_sample_count\":", length(cohort_b_index), ",",
  "\"tested_gene_count\":", nrow(counts_matrix), ",",
  "\"filtered_gene_count\":", nrow(filtered_counts), ",",
  "\"significant_gene_count\":", nrow(significant), ",",
  "\"top_gene\":", json_quote(top_gene), ",",
  "\"top_log2_fold_change\":", top_log2_fc, ",",
  "\"top_adj_p_value\":", top_adj_p, ",",
  "\"shrinkage_method\":\"apeglm\"",
  "}",
  "}"
)

cat(json)
