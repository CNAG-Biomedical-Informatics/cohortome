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

    exec:
    def compareMode = String(params.compare_mode ?: '').trim().toLowerCase() == 'true'
    def scopeSummary = compareMode ? 'Cohort A vs Cohort B' : 'current Analysis scope'
    def promptText = String(params.prompt ?: '').trim()
    def payload = [
        reply: "Nextflow dummy workflow completed for ${scopeSummary}. Workspace patients: ${params.workspace_patient_count}; scope A patients: ${params.scope_a_patient_count}; scope B patients: ${params.scope_b_patient_count}.",
        context: [
            mode: 'external_nextflow_dummy',
            scope_summary: scopeSummary,
            prompt: promptText,
            workspace_patient_count: Integer.parseInt(String(params.workspace_patient_count ?: '0')),
            scope_a_patient_count: Integer.parseInt(String(params.scope_a_patient_count ?: '0')),
            scope_b_patient_count: Integer.parseInt(String(params.scope_b_patient_count ?: '0')),
        ],
    ]
    file('result.json').text = JsonOutput.prettyPrint(JsonOutput.toJson(payload)) + '\n'
    file('summary.txt').text = "Nextflow dummy workflow\nPrompt: ${promptText}\nScope: ${scopeSummary}\n"
}

workflow {
    BUILD_RESULT()
}
