#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(DESeq2)
  library(apeglm)
  library(fgsea)
  library(msigdbr)
  library(ggplot2)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)

parse_args <- function(values) {
  parsed <- list()
  index <- 1
  while (index <= length(values)) {
    key <- values[[index]]
    if (!startsWith(key, "--")) {
      stop(sprintf("Unexpected argument: %s", key), call. = FALSE)
    }
    if (index == length(values)) {
      stop(sprintf("Missing value for argument %s", key), call. = FALSE)
    }
    parsed[[substring(key, 3)]] <- values[[index + 1]]
    index <- index + 2
  }
  parsed
}

pretty_hallmark_label <- function(value) {
  text <- gsub("^HALLMARK_", "", as.character(value))
  text <- gsub("_", " ", text)
  parts <- strsplit(tolower(text), " ", fixed = TRUE)[[1]]
  parts <- parts[nzchar(parts)]
  parts <- vapply(parts, function(part) {
    if (part %in% c("tnfa", "nfkb", "il2", "mtor", "pi3k", "akt", "dna", "uv")) {
      return(toupper(part))
    }
    paste0(toupper(substring(part, 1, 1)), substring(part, 2))
  }, character(1))
  paste(parts, collapse = " ")
}

required_arg <- function(parsed, name) {
  value <- parsed[[name]]
  if (is.null(value) || !nzchar(value)) {
    stop(sprintf("Missing required argument --%s", name), call. = FALSE)
  }
  value
}

parsed <- parse_args(args)

sample_table_path <- required_arg(parsed, "sample-table")
counts_matrix_path <- required_arg(parsed, "counts-matrix")
results_table_path <- required_arg(parsed, "results-table")
rankings_table_path <- required_arg(parsed, "rankings-table")
summary_json_path <- required_arg(parsed, "summary-json")
plot_file_path <- required_arg(parsed, "plot-file")
dataset_name <- required_arg(parsed, "dataset-name")
prompt_text <- required_arg(parsed, "prompt")

sample_table <- read.delim(sample_table_path, sep = "\t", check.names = FALSE, stringsAsFactors = FALSE)
counts_table <- read.delim(counts_matrix_path, sep = "\t", check.names = FALSE, stringsAsFactors = FALSE)

required_sample_cols <- c("sample_id", "patient_id", "cohort")
missing_sample_cols <- setdiff(required_sample_cols, names(sample_table))
if (length(missing_sample_cols)) {
  stop(sprintf("Sample table is missing required columns: %s", paste(missing_sample_cols, collapse = ", ")), call. = FALSE)
}

if (!"gene_id" %in% names(counts_table)) {
  stop("Counts matrix must include a gene_id column.", call. = FALSE)
}

sample_ids <- sample_table$sample_id
if (anyDuplicated(sample_ids)) {
  stop("Sample table contains duplicated sample IDs.", call. = FALSE)
}

patient_ids <- sample_table$patient_id
patient_counts <- table(patient_ids)
if (any(patient_counts > 1)) {
  stop(
    "DESeq2 Hallmark pathway enrichment v1 requires one sample per patient. Use a baseline-only dataset or choose one sample per patient before running.",
    call. = FALSE
  )
}

cohort_counts <- table(sample_table$cohort)
if (!all(c("A", "B") %in% names(cohort_counts))) {
  stop("Pathway enrichment requires both Cohort A and Cohort B.", call. = FALSE)
}
if (cohort_counts[["A"]] < 2 || cohort_counts[["B"]] < 2) {
  stop("Hallmark pathway enrichment requires at least two samples in Cohort A and two samples in Cohort B.", call. = FALSE)
}

count_matrix <- as.matrix(counts_table[, sample_ids, drop = FALSE])
rownames(count_matrix) <- counts_table$gene_id
storage.mode(count_matrix) <- "integer"

keep <- rowSums(count_matrix >= 10) >= 2
filtered_matrix <- count_matrix[keep, , drop = FALSE]
if (!nrow(filtered_matrix)) {
  stop("No genes passed the minimum-count filter for pathway enrichment.", call. = FALSE)
}

col_data <- data.frame(
  row.names = sample_ids,
  condition = factor(sample_table$cohort, levels = c("B", "A")),
  patient_id = patient_ids,
  stringsAsFactors = FALSE
)

dds <- DESeqDataSetFromMatrix(
  countData = filtered_matrix,
  colData = col_data,
  design = ~ condition
)
dds <- suppressMessages(DESeq(dds, quiet = TRUE))

res <- suppressMessages(results(dds, contrast = c("condition", "A", "B")))
res_shrunk <- suppressMessages(lfcShrink(dds, coef = "condition_A_vs_B", type = "apeglm"))

rank_stats <- res$stat
names(rank_stats) <- rownames(res)
rank_stats <- rank_stats[!is.na(rank_stats) & is.finite(rank_stats)]
rank_stats <- sort(rank_stats, decreasing = TRUE)
if (!length(rank_stats)) {
  stop("Unable to derive a valid ranked gene list for pathway enrichment.", call. = FALSE)
}

hallmark_df <- msigdbr(species = "Homo sapiens", collection = "H")
if (!"ensembl_gene" %in% names(hallmark_df)) {
  stop("msigdbr did not return ensembl_gene mappings required for this dataset.", call. = FALSE)
}
hallmark_df <- hallmark_df[nzchar(hallmark_df$ensembl_gene), c("gs_name", "ensembl_gene")]
hallmark_df <- unique(hallmark_df)
pathways <- split(hallmark_df$ensembl_gene, hallmark_df$gs_name)
if (!length(pathways)) {
  stop("No Hallmark pathway definitions are available for enrichment.", call. = FALSE)
}

ranked_genes <- names(rank_stats)
overlap_sizes <- vapply(pathways, function(values) length(intersect(unique(values), ranked_genes)), integer(1))
max_overlap <- if (length(overlap_sizes)) max(overlap_sizes) else 0
min_overlap_size <- if (max_overlap >= 15) 15 else if (max_overlap >= 5) 5 else 2
pathways <- pathways[overlap_sizes >= min_overlap_size]
if (!length(pathways)) {
  stop(
    sprintf(
      "No Hallmark pathways have enough overlap with the ranked genes in this dataset. Maximum overlap was %d gene%s.",
      max_overlap,
      if (identical(max_overlap, 1L)) "" else "s"
    ),
    call. = FALSE
  )
}

fgsea_res <- suppressWarnings(fgsea(pathways = pathways, stats = rank_stats, minSize = min_overlap_size, maxSize = 500, eps = 0, BPPARAM = BiocParallel::SerialParam()))
fgsea_df <- as.data.frame(fgsea_res)
if (!nrow(fgsea_df)) {
  stop("No pathway enrichment results were produced.", call. = FALSE)
}

fgsea_df$leadingEdge <- vapply(fgsea_df$leadingEdge, function(values) paste(values, collapse = ","), character(1))
fgsea_df <- fgsea_df[order(fgsea_df$padj, -abs(fgsea_df$NES), fgsea_df$pathway), , drop = FALSE]
fgsea_df$display_label <- vapply(fgsea_df$pathway, pretty_hallmark_label, character(1))
significant_mask <- !is.na(fgsea_df$padj) & fgsea_df$padj < 0.05
significant_df <- fgsea_df[significant_mask, , drop = FALSE]

rankings_df <- data.frame(
  gene_id = names(rank_stats),
  statistic = as.numeric(rank_stats),
  log2_fold_change = unname(res_shrunk[names(rank_stats), "log2FoldChange"]),
  adjusted_p_value = unname(res[names(rank_stats), "padj"]),
  stringsAsFactors = FALSE
)

write.table(fgsea_df, file = results_table_path, sep = "\t", row.names = FALSE, quote = FALSE)
write.table(rankings_df, file = rankings_table_path, sep = "\t", row.names = FALSE, quote = FALSE)

plot_df <- if (nrow(significant_df)) {
  significant_df
} else {
  fgsea_df[seq_len(min(10, nrow(fgsea_df))), , drop = FALSE]
}
plot_df <- plot_df[order(plot_df$NES), , drop = FALSE]
plot_df$direction <- ifelse(plot_df$NES >= 0, "Higher in Cohort A", "Higher in Cohort B")
plot_df$display_label <- vapply(plot_df$pathway, pretty_hallmark_label, character(1))

png(plot_file_path, width = 1200, height = 800, res = 150)
print(
  ggplot(plot_df, aes(x = reorder(display_label, NES), y = NES, fill = direction)) +
    geom_col(width = 0.75) +
    coord_flip() +
    scale_fill_manual(values = c("Higher in Cohort A" = "#2563eb", "Higher in Cohort B" = "#d9485f")) +
    labs(
      title = "Hallmark pathway enrichment",
      subtitle = dataset_name,
      x = NULL,
      y = "Normalized enrichment score (NES)",
      fill = NULL
    ) +
    theme_minimal(base_size = 12) +
    theme(
      panel.grid.major.y = element_blank(),
      legend.position = "top"
    )
)
invisible(capture.output(dev.off()))

positive_top <- significant_df[significant_df$NES > 0, , drop = FALSE]
negative_top <- significant_df[significant_df$NES < 0, , drop = FALSE]
positive_top <- positive_top[order(-positive_top$NES, positive_top$padj), , drop = FALSE]
negative_top <- negative_top[order(negative_top$NES, negative_top$padj), , drop = FALSE]

summary_payload <- list(
  dataset_name = dataset_name,
  prompt = prompt_text,
  cohort_a_sample_count = unname(cohort_counts[["A"]]),
  cohort_b_sample_count = unname(cohort_counts[["B"]]),
  filtered_gene_count = nrow(filtered_matrix),
  ranked_gene_count = length(rank_stats),
  pathway_count = nrow(fgsea_df),
  significant_pathway_count = nrow(significant_df),
  min_overlap_size = min_overlap_size,
  max_pathway_overlap = max_overlap,
  top_positive_pathways = head(positive_top$pathway, 5),
  top_negative_pathways = head(negative_top$pathway, 5)
)
summary_payload$top_positive_pathway_labels <- unname(vapply(summary_payload$top_positive_pathways, pretty_hallmark_label, character(1)))
summary_payload$top_negative_pathway_labels <- unname(vapply(summary_payload$top_negative_pathways, pretty_hallmark_label, character(1)))
writeLines(toJSON(summary_payload, auto_unbox = TRUE, pretty = TRUE), con = summary_json_path)

top_positive_text <- if (length(summary_payload$top_positive_pathway_labels)) {
  paste(summary_payload$top_positive_pathway_labels, collapse = ", ")
} else {
  "none at BH < 0.05"
}
top_negative_text <- if (length(summary_payload$top_negative_pathway_labels)) {
  paste(summary_payload$top_negative_pathway_labels, collapse = ", ")
} else {
  "none at BH < 0.05"
}

reply_lines <- c(
  "### Hallmark pathway enrichment",
  "",
  sprintf("- Dataset: %s", dataset_name),
  sprintf("- Ranked genes: %d", length(rank_stats)),
  sprintf("- Pathways tested: %d", nrow(fgsea_df)),
  sprintf("- Minimum overlap used: %d genes", min_overlap_size),
  sprintf("- Significant pathways (BH < 0.05): %d", nrow(significant_df)),
  sprintf("- Higher in Cohort A: %s", top_positive_text),
  sprintf("- Higher in Cohort B: %s", top_negative_text)
)

context_payload <- list(
  mode = "external_rscript_transcriptomics_hallmark_pathway_enrichment",
  runner = "transcriptomics_hallmark_pathway_enrichment",
  dataset_name = dataset_name,
  cohort_a_sample_count = unname(cohort_counts[["A"]]),
  cohort_b_sample_count = unname(cohort_counts[["B"]]),
  filtered_gene_count = nrow(filtered_matrix),
  ranked_gene_count = length(rank_stats),
  pathway_count = nrow(fgsea_df),
  significant_pathway_count = nrow(significant_df),
  min_overlap_size = min_overlap_size,
  max_pathway_overlap = max_overlap,
  top_positive_pathways = summary_payload$top_positive_pathways,
  top_negative_pathways = summary_payload$top_negative_pathways,
  top_positive_pathway_labels = summary_payload$top_positive_pathway_labels,
  top_negative_pathway_labels = summary_payload$top_negative_pathway_labels,
  gene_id_type = "Ensembl",
  pathway_collection = "MSigDB Hallmark"
)

cat(toJSON(list(reply = paste(reply_lines, collapse = "\n"), context = context_payload), auto_unbox = TRUE))
