args <- commandArgs(trailingOnly = TRUE)
arg <- function(name, default = "") {
  index <- match(name, args)
  if (is.na(index) || index == length(args)) default else args[[index + 1L]]
}
read_tsv <- function(path) {
  read.delim(path, sep = "\t", header = TRUE, stringsAsFactors = FALSE,
             colClasses = "character", check.names = FALSE, comment.char = "",
             na.strings = NULL, fill = FALSE)
}
write_tsv <- function(frame, path) {
  write.table(frame, path, sep = "\t", row.names = FALSE, quote = TRUE)
}
for (package in c("limma", "edgeR", "jsonlite")) {
  if (!requireNamespace(package, quietly = TRUE)) {
    stop(paste(package, "is required for limma-voom analysis."))
  }
}
suppressPackageStartupMessages(library(limma))
suppressPackageStartupMessages(library(edgeR))

dataset <- arg("--dataset-name")
samples <- read_tsv(arg("--sample-table"))
frame <- read_tsv(arg("--counts-matrix"))
if (ncol(frame) < 3L || nrow(frame) < 2L) {
  stop("Counts matrix must contain at least two genes and two samples.")
}
feature_ids <- trimws(frame[[1]])
sample_ids <- colnames(frame)[-1L]
if (any(!nzchar(feature_ids)) || anyDuplicated(feature_ids) ||
    any(!nzchar(sample_ids)) || anyDuplicated(sample_ids)) {
  stop("Count matrix gene and sample identifiers must be non-empty and unique.")
}
counts <- as.matrix(frame[, -1L, drop = FALSE])
suppressWarnings(storage.mode(counts) <- "numeric")
rownames(counts) <- feature_ids
if (any(!is.finite(counts)) || any(counts < 0)) {
  stop("RSEM expected counts must be finite and non-negative.")
}
required <- c("sample_id", "patient_id", "cohort")
if (!all(required %in% names(samples))) {
  stop("Sample table must contain sample_id, patient_id, and cohort.")
}
for (name in required) samples[[name]] <- trimws(samples[[name]])
if (any(!nzchar(samples$sample_id)) || anyDuplicated(samples$sample_id) ||
    any(!nzchar(samples$patient_id)) || anyDuplicated(samples$patient_id)) {
  stop("limma-voom requires unique samples and one sample per non-empty patient identifier.")
}
if (nrow(samples) != ncol(counts) || !setequal(samples$sample_id, sample_ids)) {
  stop("Sample metadata and count matrix must contain exactly the same selected samples.")
}
samples <- samples[match(sample_ids, samples$sample_id), , drop = FALSE]
if (any(!samples$cohort %in% c("A", "B")) ||
    sum(samples$cohort == "A") < 2L || sum(samples$cohort == "B") < 2L) {
  stop("limma-voom requires at least two samples per cohort, labelled A and B.")
}

covariates_path <- arg("--covariates-file")
if (!nzchar(covariates_path)) {
  stop("An explicit covariate specification file is required, including for unadjusted models. Regenerate run inputs with the updated adapter.")
}
specs <- read_tsv(covariates_path)
if (!all(c("name", "type") %in% names(specs)) || anyDuplicated(specs$name) ||
    any(!nzchar(specs$name)) || any(!specs$type %in% c("numeric", "categorical")) ||
    any(specs$name %in% c("cohort", "sample_id", "patient_id", "group_label"))) {
  stop("Covariates require unique, non-reserved names and explicit numeric or categorical types.")
}
if (any(!specs$name %in% names(samples))) {
  stop("Sample table is missing declared transcriptomics covariates.")
}
design_data <- data.frame(cohort = factor(samples$cohort, levels = c("B", "A")),
                          row.names = samples$sample_id)
internal_names <- if (nrow(specs)) paste0("covariate_", seq_len(nrow(specs))) else character()
covariate_records <- vector("list", nrow(specs))
for (i in seq_len(nrow(specs))) {
  name <- specs$name[[i]]
  values <- trimws(samples[[name]])
  if (any(is.na(values) | tolower(values) %in% c("", "na", "n/a", "nan", "null", "none", "."))) {
    stop("limma-voom requires complete values for every declared covariate; no samples are dropped automatically.")
  }
  if (specs$type[[i]] == "numeric") {
    values <- suppressWarnings(as.numeric(values))
    if (any(!is.finite(values))) stop("Numeric transcriptomics covariates must be finite numbers.")
  } else {
    values <- factor(values, levels = sort(unique(values)))
  }
  if (length(unique(values)) < 2L) {
    stop("A declared transcriptomics covariate is constant in scope; review the model rather than dropping terms automatically.")
  }
  design_data[[internal_names[[i]]]] <- values
  covariate_records[[i]] <- list(name = name, type = specs$type[[i]],
                                  design_name = internal_names[[i]], levels = levels(values))
}
formula <- reformulate(c("cohort", internal_names))
factor_columns <- vapply(design_data, is.factor, logical(1))
contrast_coding <- lapply(design_data[factor_columns], function(x) contr.treatment(levels(x), base = 1))
design <- model.matrix(formula, design_data, contrasts.arg = contrast_coding)
coefficient <- "cohortA"
if (!coefficient %in% colnames(design)) stop("The Cohort A minus Cohort B coefficient is unavailable.")
design_rank <- qr(design)$rank
if (design_rank < ncol(design)) {
  stop("The transcriptomics design is rank deficient; cohort and declared covariates cannot be estimated independently.")
}
residual_df <- nrow(design) - design_rank
if (residual_df < 1L) stop("The transcriptomics design has no residual degrees of freedom.")

input_gene_count <- nrow(counts)
if (any(colSums(counts) <= 0)) stop("Every selected sample must have a positive library size.")
dge <- DGEList(counts = counts)
keep <- filterByExpr(dge, design = design)
dge <- dge[keep, , keep.lib.sizes = FALSE]
if (nrow(dge) < 2L) stop("Too few genes remain after expression filtering.")
if (any(dge$samples$lib.size <= 0)) stop("Expression filtering left a zero-library sample.")
dge <- calcNormFactors(dge, method = "TMM")
voom_values <- voom(dge, design, plot = FALSE)
fit <- eBayes(lmFit(voom_values, design))
res <- topTable(fit, coef = coefficient, number = Inf, sort.by = "P", adjust.method = "BH")
result <- data.frame(gene_id = rownames(res), log2_fold_change = res$logFC,
                     t = res$t, p_value = res$P.Value, adj_p_value = res$adj.P.Val,
                     stringsAsFactors = FALSE)
result$neg_log10_p <- -log10(pmax(result$p_value, 1e-300))
write_tsv(result, arg("--results-table"))
write_tsv(result[, c("gene_id", "log2_fold_change", "p_value", "adj_p_value", "neg_log10_p")],
          arg("--volcano-table"))

job_dir <- arg("--job-dir", dirname(arg("--results-table")))
write_tsv(data.frame(sample_id = sample_ids, design, check.names = FALSE),
          file.path(job_dir, "design_matrix.tsv"))
write_tsv(data.frame(coefficient = colnames(design), weight = as.integer(colnames(design) == coefficient)),
          file.path(job_dir, "contrast.tsv"))
write_tsv(data.frame(gene_id = feature_ids, retained = keep), file.path(job_dir, "gene_filter.tsv"))
write_tsv(data.frame(sample_id = sample_ids, library_size = dge$samples$lib.size,
                     normalization_factor = dge$samples$norm.factors),
          file.path(job_dir, "normalization_factors.tsv"))
adjustment_status <- if (nrow(specs)) "covariate_adjusted" else "unadjusted_exploratory"
model_record <- list(
  formula = paste(deparse(formula), collapse = " "), coefficient = coefficient,
  contrast = "Cohort A - Cohort B", reference_cohort = "B", adjustment_status = adjustment_status,
  covariates = covariate_records, design_rank = design_rank, residual_degrees_of_freedom = residual_df,
  missing_covariate_policy = "reject_selected_missing", expression_filter = "edgeR::filterByExpr(design)",
  normalization = "TMM", multiple_testing = "BH over tested genes",
  input_gene_count = input_gene_count, tested_gene_count = nrow(dge),
  versions = list(R = as.character(getRversion()), limma = as.character(packageVersion("limma")),
                  edgeR = as.character(packageVersion("edgeR")), jsonlite = as.character(packageVersion("jsonlite")))
)
writeLines(jsonlite::toJSON(model_record, auto_unbox = TRUE, null = "null", pretty = TRUE, digits = NA),
           file.path(job_dir, "model.json"))
writeLines(capture.output(sessionInfo()), file.path(job_dir, "session_info.txt"))

png(arg("--plot-file"), width = 960, height = 720)
plot(result$log2_fold_change, result$neg_log10_p, pch = 16,
     col = ifelse(result$adj_p_value < .05, "#d9485f", "#94a3b8"),
     xlab = "log2 fold change (Cohort A - Cohort B)", ylab = "-log10 p-value",
     main = paste("limma-voom differential expression:", dataset))
abline(v = 0, lty = 2)
invisible(dev.off())

sig <- sum(result$adj_p_value < .05, na.rm = TRUE)
top <- result[1L, ]
summary <- list(dataset_name = dataset, cohort_a_sample_count = sum(samples$cohort == "A"),
                cohort_b_sample_count = sum(samples$cohort == "B"), input_gene_count = input_gene_count,
                tested_gene_count = nrow(dge), filtered_gene_count = nrow(dge), significant_gene_count = sig,
                top_gene = top$gene_id, top_log2_fold_change = top$log2_fold_change,
                top_adj_p_value = top$adj_p_value, method = "limma-voom",
                adjustment_status = adjustment_status, covariates_used = as.list(unname(specs$name)),
                analysis_covariate_types = setNames(as.list(specs$type), specs$name),
                coefficient = coefficient, contrast = "Cohort A - Cohort B", design_rank = design_rank,
                residual_degrees_of_freedom = residual_df)
writeLines(jsonlite::toJSON(summary, auto_unbox = TRUE, null = "null", digits = NA), arg("--summary-json"))
adjustment_text <- if (nrow(specs)) paste("Adjusted for", paste(specs$name, collapse = ", ")) else "Unadjusted exploratory model"
reply <- paste0("limma-voom differential expression completed for ", dataset, ". Tested ", nrow(dge),
                " of ", input_gene_count, " input genes; ", sig, " passed BH < 0.05. ",
                adjustment_text, ". Contrast: Cohort A minus Cohort B.")
context <- c(list(mode = "external_rscript_transcriptomics_limma_voom_differential_expression",
                  runner = "transcriptomics_limma_voom_differential_expression"), summary)
cat(jsonlite::toJSON(list(reply = reply, context = context), auto_unbox = TRUE, null = "null", digits = NA))
