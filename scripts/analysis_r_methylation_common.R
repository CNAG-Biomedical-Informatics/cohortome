args <- commandArgs(trailingOnly = TRUE)

arg_value <- function(name, default = "") {
  index <- match(name, args)
  if (is.na(index) || index == length(args)) default else args[[index + 1]]
}

read_required_tsv <- function(path) {
  if (!nzchar(path) || !file.exists(path)) {
    stop("A required job input is unavailable.")
  }
  read.delim(
    path,
    sep = "\t",
    header = TRUE,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    quote = "\"",
    comment.char = ""
  )
}

read_covariate_specs <- function(path) {
  frame <- read_required_tsv(path)
  if (!all(c("name", "type") %in% names(frame))) {
    stop("Methylation covariate specifications must contain name and type columns.")
  }
  frame$name <- trimws(as.character(frame$name))
  frame$type <- tolower(trimws(as.character(frame$type)))
  if (any(!nzchar(frame$name)) || anyDuplicated(frame$name)) {
    stop("Methylation covariate specifications contain empty or duplicate names.")
  }
  if (any(!frame$type %in% c("numeric", "categorical"))) {
    stop("Methylation covariates must be typed as numeric or categorical.")
  }
  frame[, c("name", "type"), drop = FALSE]
}

detect_matrix_separator <- function(line) {
  separators <- c("\t", ";", ",")
  counts <- vapply(
    separators,
    function(separator) length(scan(
      text = line,
      what = character(),
      sep = separator,
      quote = "\"",
      comment.char = "",
      quiet = TRUE
    )),
    integer(1)
  )
  separators[[which.max(counts)]]
}

matrix_header <- function(path) {
  if (!nzchar(path) || !file.exists(path)) {
    stop("The manifest-backed methylation matrix is unavailable.")
  }
  connection <- file(path, open = "r", encoding = "UTF-8")
  on.exit(close(connection))
  line <- readLines(connection, n = 1L, warn = FALSE)
  if (!length(line) || !nzchar(line[[1]])) {
    stop("The manifest-backed methylation matrix is empty.")
  }
  separator <- detect_matrix_separator(line[[1]])
  columns <- scan(
    text = line[[1]],
    what = character(),
    sep = separator,
    quote = "\"",
    comment.char = "",
    quiet = TRUE
  )
  columns[[1]] <- sub("^\ufeff", "", columns[[1]])
  if (length(columns) < 3L) {
    stop("The methylation matrix needs a feature column and at least two sample columns.")
  }
  list(columns = columns, separator = separator)
}

stream_methylation_matrix <- function(path, sample_ids, callback, chunk_size = 2000L) {
  header <- matrix_header(path)
  source_sample_ids <- header$columns[-1]
  if (anyDuplicated(source_sample_ids)) {
    stop("The methylation matrix contains duplicate sample identifiers.")
  }
  selected_positions <- match(sample_ids, source_sample_ids)
  if (anyNA(selected_positions)) {
    stop("The methylation matrix columns do not align with the scoped sample table.")
  }
  source_positions <- selected_positions + 1L
  column_classes <- rep("NULL", length(header$columns))
  column_classes[[1]] <- "character"
  column_classes[source_positions] <- "numeric"

  connection <- file(path, open = "r", encoding = "UTF-8")
  on.exit(close(connection))
  invisible(readLines(connection, n = 1L, warn = FALSE))
  observed_rows <- 0L
  seen_feature_ids <- new.env(hash = TRUE, parent = emptyenv())
  repeat {
    lines <- readLines(connection, n = as.integer(chunk_size), warn = FALSE)
    if (!length(lines)) {
      break
    }
    lines <- lines[nzchar(lines)]
    if (!length(lines)) {
      next
    }
    frame <- read.table(
      text = lines,
      sep = header$separator,
      header = FALSE,
      col.names = header$columns,
      colClasses = column_classes,
      stringsAsFactors = FALSE,
      check.names = FALSE,
      quote = "\"",
      comment.char = "",
      na.strings = c("", "NA", "NaN"),
      fill = FALSE
    )
    names(frame) <- c("feature_id", source_sample_ids[selected_positions])
    frame$feature_id <- trimws(as.character(frame$feature_id))
    if (any(!nzchar(frame$feature_id))) {
      stop("The methylation matrix contains an empty feature identifier.")
    }
    for (feature_id in frame$feature_id) {
      if (exists(feature_id, envir = seen_feature_ids, inherits = FALSE)) {
        stop("The methylation matrix contains duplicate CpG identifiers.")
      }
      assign(feature_id, TRUE, envir = seen_feature_ids)
    }
    callback(frame)
    observed_rows <- observed_rows + nrow(frame)
  }
  observed_rows
}

prepare_sample_table <- function(path, require_compare = FALSE) {
  samples <- read_required_tsv(path)
  required <- c("sample_id", "patient_id", "cohort")
  if (!all(required %in% names(samples))) {
    stop("The scoped sample table must contain sample_id, patient_id, and cohort columns.")
  }
  for (name in required) {
    samples[[name]] <- trimws(as.character(samples[[name]]))
  }
  if (any(!nzchar(samples$sample_id)) || anyDuplicated(samples$sample_id)) {
    stop("The scoped sample table contains empty or duplicate sample identifiers.")
  }
  if (any(!nzchar(samples$patient_id))) {
    stop("The scoped sample table contains an empty patient identifier.")
  }
  if (require_compare) {
    if (anyDuplicated(samples$patient_id)) {
      stop("Differential methylation requires one sample per patient.")
    }
    if (sum(samples$cohort == "A") < 2L || sum(samples$cohort == "B") < 2L) {
      stop("Differential methylation requires at least two samples in each cohort.")
    }
    if (any(!samples$cohort %in% c("A", "B"))) {
      stop("Differential methylation accepts only Cohort A and Cohort B samples.")
    }
  }
  samples
}

bounded_ranked_indices <- function(total_count, limit, priority_fraction = 0.9) {
  total_count <- as.integer(total_count)
  limit <- as.integer(limit)
  if (total_count <= 0L || limit <= 0L) {
    return(integer())
  }
  if (total_count <= limit) {
    return(seq_len(total_count))
  }
  priority_count <- max(1L, min(total_count, floor(limit * priority_fraction)))
  priority_indices <- seq_len(priority_count)
  background_candidates <- seq.int(priority_count + 1L, total_count)
  background_slots <- limit - priority_count
  if (background_slots <= 0L) {
    return(priority_indices[seq_len(limit)])
  }
  background_positions <- unique(as.integer(round(seq(
    1L,
    length(background_candidates),
    length.out = background_slots
  ))))
  background_indices <- background_candidates[background_positions]
  if (length(background_indices) < background_slots) {
    extra <- setdiff(background_candidates, background_indices)
    background_indices <- c(background_indices, head(extra, background_slots - length(background_indices)))
  }
  c(priority_indices, background_indices)
}

write_json_file <- function(path, payload) {
  writeLines(
    jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", na = "null", digits = 10),
    con = path,
    useBytes = TRUE
  )
}

emit_result <- function(reply, context) {
  cat(jsonlite::toJSON(list(reply = reply, context = context), auto_unbox = TRUE, null = "null", na = "null", digits = 10))
}
