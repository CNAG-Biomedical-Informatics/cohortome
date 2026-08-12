args <- commandArgs(trailingOnly = TRUE)
arg <- function(name, default = "") { i <- match(name, args); if (is.na(i) || i == length(args)) default else args[[i + 1]] }
quote_json <- function(x) { x <- gsub("\\\\", "\\\\\\\\", as.character(x)); x <- gsub("\"", "\\\\\"", x); paste0("\"", x, "\"") }
read_tsv <- function(path) read.delim(path, sep = "\t", header = TRUE, stringsAsFactors = FALSE, check.names = FALSE)
if (!requireNamespace("limma", quietly = TRUE) || !requireNamespace("edgeR", quietly = TRUE)) stop("limma and edgeR are required for limma-voom analysis.")
if (!requireNamespace("jsonlite", quietly = TRUE)) stop("jsonlite is required for limma-voom analysis.")
suppressPackageStartupMessages(library(limma)); suppressPackageStartupMessages(library(edgeR)); suppressPackageStartupMessages(library(jsonlite))
dataset <- arg("--dataset-name"); samples <- read_tsv(arg("--sample-table")); frame <- read_tsv(arg("--counts-matrix"))
if (ncol(frame) < 3) stop("Counts matrix must contain a feature column and at least two samples.")
counts <- as.matrix(frame[, -1, drop = FALSE]); storage.mode(counts) <- "numeric"; rownames(counts) <- frame[[1]]
if (any(!is.finite(counts)) || any(counts < 0)) stop("RSEM expected counts must be finite and non-negative.")
samples <- samples[match(colnames(counts), samples$sample_id), , drop = FALSE]
if (any(is.na(samples$sample_id)) || anyDuplicated(samples$patient_id)) stop("Sample table does not align or contains repeated patients.")
samples$cohort <- factor(samples$cohort, levels = c("B", "A")); if (sum(samples$cohort == "A") < 2 || sum(samples$cohort == "B") < 2) stop("limma-voom requires at least two samples per cohort.")
dge <- DGEList(counts = counts); keep <- filterByExpr(dge, group = samples$cohort); dge <- dge[keep, , keep.lib.sizes = FALSE]; if (nrow(dge) < 2) stop("Too few genes remain after expression filtering.")
dge <- calcNormFactors(dge); design <- model.matrix(~ samples$cohort); fit <- eBayes(lmFit(voom(dge, design, plot = FALSE), design)); coefficient <- colnames(design)[ncol(design)]
res <- topTable(fit, coef = coefficient, number = Inf, sort.by = "P"); result <- data.frame(gene_id = rownames(res), log2_fold_change = res$logFC, t = res$t, p_value = res$P.Value, adj_p_value = res$adj.P.Val, stringsAsFactors = FALSE); result$neg_log10_p <- -log10(pmax(result$p_value, 1e-300))
write.table(result, arg("--results-table"), sep = "\t", row.names = FALSE, quote = FALSE); write.table(result[, c("gene_id", "log2_fold_change", "p_value", "adj_p_value", "neg_log10_p")], arg("--volcano-table"), sep = "\t", row.names = FALSE, quote = FALSE)
png(arg("--plot-file"), width = 960, height = 720); plot(result$log2_fold_change, result$neg_log10_p, pch = 16, col = ifelse(result$adj_p_value < .05, "#d9485f", "#94a3b8"), xlab = "log2 fold change (Cohort A - Cohort B)", ylab = "-log10 p-value", main = paste("limma-voom differential expression:", dataset)); abline(v = 0, lty = 2); invisible(dev.off())
sig <- sum(result$adj_p_value < .05, na.rm = TRUE); top <- if (nrow(result)) result[1, ] else NULL; summary <- list(dataset_name = dataset, cohort_a_sample_count = sum(samples$cohort == "A"), cohort_b_sample_count = sum(samples$cohort == "B"), tested_gene_count = nrow(counts), filtered_gene_count = nrow(dge), significant_gene_count = sig, top_gene = if (is.null(top)) "n/a" else as.character(top$gene_id), top_log2_fold_change = if (is.null(top)) 0 else top$log2_fold_change, top_adj_p_value = if (is.null(top)) 1 else top$adj_p_value, method = "limma-voom")
writeLines(toJSON(summary, auto_unbox = TRUE), arg("--summary-json")); reply <- paste0("limma-voom differential expression completed for ", dataset, ". Tested ", nrow(counts), " genes and retained ", nrow(dge), "; ", sig, " passed BH < 0.05."); context <- c(list(mode = "external_rscript_transcriptomics_limma_voom_differential_expression", runner = "transcriptomics_limma_voom_differential_expression"), summary); cat(paste0("{\"reply\":", quote_json(reply), ",\"context\":", toJSON(context, auto_unbox = TRUE), "}"))
