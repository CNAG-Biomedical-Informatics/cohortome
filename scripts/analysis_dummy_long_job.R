args <- commandArgs(trailingOnly = TRUE)

read_arg <- function(name, default = "") {
  idx <- match(name, args)
  if (is.na(idx) || idx >= length(args)) {
    return(default)
  }
  args[[idx + 1]]
}

json_quote <- function(value) {
  escaped <- gsub("\\\\", "\\\\\\\\", value)
  escaped <- gsub("\"", "\\\\\"", escaped)
  escaped <- gsub("\n", "\\\\n", escaped)
  paste0("\"", escaped, "\"")
}

prompt <- read_arg("--prompt", "")
sleep_seconds_raw <- read_arg("--sleep-seconds", "60")
sleep_seconds <- suppressWarnings(as.numeric(sleep_seconds_raw))
if (is.na(sleep_seconds) || sleep_seconds < 0) {
  sleep_seconds <- 60
}

Sys.sleep(sleep_seconds)

reply <- paste0(
  "### External R long-running demo\n\n",
  "- Completed a curated external background job.\n",
  "- Simulated runtime: ", sleep_seconds, " seconds.\n",
  if (nzchar(prompt)) paste0("- Prompt: ", prompt, "\n") else ""
)

json <- paste0(
  "{",
  "\"reply\":", json_quote(reply), ",",
  "\"context\":{",
  "\"mode\":\"external_rscript_long_job\",",
  "\"runner\":\"dummy_long_job\",",
  "\"prompt\":", json_quote(prompt), ",",
  "\"simulated_runtime_seconds\":", sleep_seconds,
  "}",
  "}"
)

cat(json)
