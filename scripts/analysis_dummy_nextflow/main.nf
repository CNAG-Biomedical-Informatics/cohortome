import groovy.json.JsonOutput

params.job_dir = '.'
params.result_json = "${params.job_dir}/result.json"
params.summary_txt = "${params.job_dir}/summary.txt"
params.prompt = ''
params.compare_mode = 'false'
params.workspace_patient_count = '0'
params.scope_a_patient_count = '0'
params.scope_b_patient_count = '0'

process BUILD_RESULT {
    publishDir params.job_dir, mode: 'copy', overwrite: true

    output:
    path 'result.json'
    path 'summary.txt'

    script:
    def compareMode = (params.compare_mode ?: '').toString().trim().toLowerCase() == 'true'
    def scopeSummary = compareMode ? 'Cohort A vs Cohort B' : 'current Analysis scope'
    def promptText = (params.prompt ?: '').toString().trim()
    def workspacePatientCount = Integer.parseInt((params.workspace_patient_count ?: '0').toString())
    def scopeAPatientCount = Integer.parseInt((params.scope_a_patient_count ?: '0').toString())
    def scopeBPatientCount = Integer.parseInt((params.scope_b_patient_count ?: '0').toString())
    def payload = [
        reply: "Nextflow dummy workflow completed for ${scopeSummary}. Workspace patients: ${workspacePatientCount}; scope A patients: ${scopeAPatientCount}; scope B patients: ${scopeBPatientCount}.",
        context: [
            mode: 'external_nextflow_dummy',
            scope_summary: scopeSummary,
            prompt: promptText,
            workspace_patient_count: workspacePatientCount,
            scope_a_patient_count: scopeAPatientCount,
            scope_b_patient_count: scopeBPatientCount,
        ],
    ]
    def payloadJson = JsonOutput.prettyPrint(JsonOutput.toJson(payload))
    [
        "cat > result.json <<'JSON'",
        payloadJson,
        "JSON",
        "cat > summary.txt <<'TXT'",
        "Nextflow dummy workflow",
        "Prompt: ${promptText}",
        "Scope: ${scopeSummary}",
        "TXT",
    ].join('\n')
}

workflow {
    BUILD_RESULT()
}
