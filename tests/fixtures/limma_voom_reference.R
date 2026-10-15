# Independent specification for the synthetic batch/age fixture in test_limma_voom.py.
# This script does not source or invoke the COHORTome runner.
arguments <- commandArgs(trailingOnly = TRUE)
suppressPackageStartupMessages(library(edgeR))
suppressPackageStartupMessages(library(limma))
metadata <- read.delim(arguments[[1]], check.names = FALSE)
input <- read.delim(arguments[[2]], check.names = FALSE, row.names = 1)
metadata <- metadata[order(metadata$sample_id), ]
expression <- as.matrix(input[, metadata$sample_id])
model_data <- data.frame(cohort = factor(metadata$cohort, levels = c("B", "A")),
                         batch = factor(metadata$batch, levels = c("101", "102", "103")),
                         age = as.numeric(metadata$age))
model <- model.matrix(~ cohort + batch + age, model_data)
data <- DGEList(counts = expression)
retained <- filterByExpr(data, design = model)
data <- data[retained, , keep.lib.sizes = FALSE]
data <- calcNormFactors(data, method = "TMM")
weighted_expression <- voom(data, model, plot = FALSE)
fitted <- lmFit(weighted_expression, model)
moderated <- eBayes(fitted)
result <- topTable(moderated, coef = "cohortA", number = Inf, sort.by = "none", adjust.method = "BH")
write.table(data.frame(gene_id = rownames(result), log2_fold_change = result$logFC,
                       t = result$t, p_value = result$P.Value, adj_p_value = result$adj.P.Val),
             arguments[[3]], sep = "\t", row.names = FALSE, quote = TRUE)
