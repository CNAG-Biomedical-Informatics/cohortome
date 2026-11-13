---
sidebar_position: 2
---

# Dashboard

import MultimodalWalkthrough from '@site/src/components/MultimodalWalkthrough';

Check the available records and measurements before selecting patients or
running an analysis.

On a fresh installation, **Open demo** prepares and opens the bundled synthetic
cross-sectional dataset. In a shared web deployment, preparing a dataset requires
an administrator; other users can open it once prepared. **Choose datasets**
opens the workspace selector instead.

![Clinical dashboard using the bundled synthetic dataset](/img/screenshots/workspace-shell.png)

The view buttons are grouped by task. **Explore data** and **Build a cohort**
are labels, not extra tabs; every view opens directly.

| Group | View | Use it to |
| --- | --- | --- |
| Explore data | Clinical | Check patient counts, visits, diseases, and medications |
| | Timeline | Inspect clinical records and linked samples over time |
| | Assays | Inspect laboratory matrices, feature counts, and coverage |
| | Imaging | Find DICOM studies, open the viewer, and inspect derived measurements |
| Build a cohort | Patients | Filter by clinical or biosample information and save the matching patients |
| | Multimodal | Refine patients by data availability, then save a cohort |

## Patient overview

Open **Patients** to browse the first 20 patients. Use **Next** and **Previous**,
or add a patient ID or ClarID to the filter draft.
Selecting a patient opens their **Timeline**.
Identical IDs from different datasets remain separate.

### Filter by clinical values

Choose **Add clinical filter**, browse the available fields and set a condition.
Combine rules with disease, sample-origin and ID filters. Patients and Multimodal
share the same draft, shown as removable labels in both views.

![Available clinical filter fields in the synthetic longitudinal demo](/img/screenshots/clinical-filter-fields.png)

| Action | Effect |
| --- | --- |
| Edit filters | Marks **Unapplied changes**; the current scope stays unchanged. |
| **Apply to scope** | Evaluates all conditions together and updates the patient scope. |
| **Discard changes** | Restores the filters used by the current scope. |
| **Clear filters**, then **Apply to scope** | Returns to the full workspace. |

![A disease filter awaiting Apply to scope; the patient table still shows the applied group](/img/screenshots/cohort-scope-draft.png)

The table and **Save patients as cohort** count describe the applied group,
including **all matches**, not just the page. Click a clinical filter to edit
it. For **is any of**, click recorded values to select
or deselect them; selected values are highlighted.

Field cards show source datasets and units. Categories offer recorded choices;
numeric fields show their observed range, not a clinical reference range.
Patients from datasets without the field are excluded. Disease-chip counts
describe the workspace, not the clinically filtered group.

:::note[What a match means]

All rules must match at **any recorded visit**, possibly at different visits.
A numeric range must match one observation. **Not recorded** does not mean
a condition is absent. Saving keeps the patients and filter description;
membership does not change automatically later.

:::

**Clear clinical filters** removes only those rules. If source data change,
**Reload clinical filters** clears them so you can choose from the updated fields.

For numeric ranges, adjust the sliders or enter exact limits before applying
the draft. Recorded age does not require a date of birth. Age filters
match any recorded visit, not a calculated current age.

### Find patients by sample origin

When the dataset supplies biosample metadata, use **Sample origin** to choose a
recorded tissue or material, such as blood or skin. Combine it with disease or
ID filters. Continue in **Multimodal** to add data-availability requirements,
then **Apply to scope**. Saving the group as a cohort is optional.

![Patients filtered by blood sample origin in the public CINECA UK1 + GEUVADIS demo](/img/screenshots/dashboard-patients.png)

*The CINECA demo combines synthetic clinical attributes with public molecular data.*

:::note[Patients, not individual specimens]

A patient with several matching biosamples is counted once. The selection keeps
all that patient's samples; it does not restrict an analysis to the chosen tissue.
Missing origin metadata means **unknown**, not that the patient has no samples.

:::

You can also [query recorded sample origins](./query.md#find-patients-by-sample-origin)
without an LLM.

### Inspect samples and clinical records

The Timeline inventory lists clinical records alongside linked sample IDs and assays. Dates, visits, specimen
material, and ClarIDs appear when supplied. **Not recorded** means that
the source metadata does not provide the field.

| In the ClarID column | What it describes |
| --- | --- |
| Clinical row | The subject |
| Assay row with an explicit biosample link | The linked specimen |

Click **ClarID** to read its decoded fields. Biosample labels can describe tissue,
sample type and assay when supplied. **Different specimens may share a ClarID**;
the source specimen ID, not the label, identifies the biosample.

![Clinical and assay inventory with subject and biosample ClarIDs in the CINECA UK1 + GEUVADIS demo](/img/screenshots/dashboard-biosamples.png)

Clinical rows use the same table layout as assays: visit identifier, data type,
recorded time and counts of clinical entries. **View clinical values** expands
that row to show diagnoses, phenotypes, measurements and treatments, including
ontology IDs. Selecting a clinical marker opens its record's values automatically.
The same table groups clinical records and samples under their exact visit
identifier, in natural order (visit 2 before visit 10). Samples retain their
assay grouping within each visit. Entries without a visit identifier appear
under **Visit not recorded**. Matching dates alone do not establish a visit link.
**Technical details** holds source metadata and the complete BFF JSON,
collapsed by default. Clinical records are loaded in batches of 20;
use **Load more records** for longer histories.

<details>
<summary>See the visit-grouped clinical and assay inventory</summary>

![Synthetic patient's clinical records grouped by naturally ordered visits in the shared inventory](/img/screenshots/dashboard-patient-visits.png)

*Clinical records and assays share one inventory. Missing visit links remain explicit.*

</details>

Selecting a clinical marker opens that timepoint's record. **All clinical
timepoints** restores the patient's full record list. The sample inventory
continues to show all linked samples for the patient; selecting a clinical
marker does not imply that every assay belongs to that visit.

:::note[What the inventory tells you]

It lists data available in COHORTome, not every assay ever performed. Missing
links and unavailable assays are reported as limitations. Sample IDs do not
necessarily represent distinct biological specimens.

:::

## Timeline

1. Choose one dataset or all active datasets.
2. Use **Has data** to require a data type, such as Proteomics.
3. Select several types to require all of them.
4. Click a marker, patient name, or grey span for details.

The plot shows 40 patients per page. Legend controls change visible markers,
not which patients match the filter.

Grey spans run from the earliest to the latest recorded observation; they do
not imply continuous monitoring. Undated assays appear under **Date not
recorded**, rather than being assigned an estimated visit. Dates are calendar
dates, not aligned study visits.

OLINK appears under Proteomics. Imaging markers represent derived measurements;
DICOM studies are listed in Imaging.

## Clinical dashboard

Check patient and timepoint totals, disease and medication distributions, and
visits per patient. These summaries describe the loaded records; missing
medication data does not establish that a patient takes no medication.

Choose **Apply to scope** from a saved cohort or
Query's **More options** to summarize that group. The scope bar shows the selected
patient count and how many have clinical records. **Show full workspace** asks
for confirmation before clearing the shared scope. Existing chats keep their
captured selections.

All clinical records for the selected patients are included, even when the
selection came from a particular sample. Disease and medication counts count
each patient once per category; categories can overlap.

### Clinical characteristics

Switch to **Table** for summary statistics, with one dataset shown at a time.
The table follows the **applied scope**, just like the charts.

![Clinical characteristics of the selected synthetic patients, with recorded and missing counts](/img/screenshots/clinical-characteristics.png)

| Values | Summary |
| --- | --- |
| Categories | Patients and percentages; a patient may appear in several categories |
| Numbers | Median and interquartile range of per-patient medians across visits |
| Recorded / Missing | Patients with / without a usable value |

These are **not baseline statistics**. Use **?** for the calculation details.
Clinical, Timeline, Assays and Imaging follow the applied scope. New chats inherit
it; existing chats, completed runs and saved cohorts keep their own selections.
If applying filters fails, the previous scope remains active.

## Assays dashboard

Check each assay's source dataset, modality, feature inventory, and sample
coverage. In a multi-dataset workspace, confirm that the assay you intend to
analyse comes from the expected dataset.

Laboratory assay totals exclude imaging. Use Imaging for studies and derived
imaging measurements.

![Assay overview distinguishing patient coverage by modality from assay counts in the synthetic workspace](/img/screenshots/dashboard-assays.png)

Choose **Browse variants** on a prepared panel to search variants, inspect
annotations and save carriers as a cohort. Genotype dosage matrices do not
offer this browser.

![Variant browser showing fictional variants, call counts and the carrier-cohort action](/img/screenshots/variant-browser.png)

*The patient-origin and variant examples shown here use a fictional documentation
fixture, not an additional dataset included with the app.*

## Imaging dashboard

Open a listed study when its viewer is available. COHORTome launches OHIF;
pixels remain in the configured DICOM service.

A study listing confirms that metadata was registered, not that the image server
is reachable. Use the viewer status and error message to check access.
Derived imaging measurements are separate matrices produced outside COHORTome.

## Multimodal dashboard

<MultimodalWalkthrough />

### Find shared coverage

Patients and Multimodal edit **one shared filter draft**. Switch between them
freely; no transfer step is needed. **Apply to scope** is available in either
view. Until applied, the displayed counts and results describe the previous scope.

Start from all workspace patients or an existing saved patient cohort. Select
one or more diseases if needed (patients may match any selected disease), then
select the required data types and choose:

- **At least these types:** require each selected type; allow additional data.
- **Only these types:** exclude additional non-clinical types.

Clinical records are required only when Clinical is selected.
For example, select **Systemic Lupus Erythematosus**, **Transcriptomics** and
**DNA methylation** to find SLE patients with both assays. Disease filters use
recorded diagnoses across available visits, not necessarily at assay collection.
Sample cohorts are not offered as starting groups because this view matches patients.

The combination plot shows observed data-type combinations and their patient
counts. Filled dots indicate available types. Click a count to inspect a
combination in the draft, apply it, then open **Matching patients**.

Choose **Save cohort** to keep the matching patients. Membership includes the
source dataset, so repeated IDs across datasets do not merge into one patient.
See [saved cohorts](saved-cohorts-and-handoffs.md) to export or analyse the group.

![Multimodal selection of SLE patients with transcriptomics and methylation, showing 28 matching synthetic patients and the Save cohort action](/img/screenshots/multimodal-selection.png)

*The synthetic example matches 28 patients. The combination rows show which additional data types they have.*

:::warning[Patient overlap is not sample matching]

Having two modalities for a patient does not establish that measurements came
from the same specimen or visit. Read **Coverage limitations** and check the
sample links before analysis. Coverage is not a quality-control result.

:::

### Coverage and feature preview

**Missingness in selected features** shows the six selected columns with the
highest missing fractions in a bounded sample-level matrix. It does not inspect
every feature in every source assay. Missing values may reflect absent
measurements or unmatched IDs.

Choose **Compare measurements in Analysis** to select two features and run an
association. [Analysis](analysis.md#compare-two-measurements) explains the
matching rules and statistical limitations.

<details>
<summary>How coverage is calculated</summary>

Coverage uses clinical IDs, assay matrix headers, declared sample linkage, and
study metadata—not assay values. Invalid or undeclared links are excluded and
reported. Patients with linked assays but no clinical record can contribute to
coverage, but have no clinical record to inspect.

The selected-feature matrix joins by exact sample/timepoint ID. It does not
extract numeric features from DICOM pixels. Imaging studies and imaging-derived
measurements are separate data types; OLINK is grouped under Proteomics.

Patient lookup, timelines, and multimodal coverage require Detailed access to
all selected datasets.

</details>

## If the dashboard does not load

Use **Retry dashboard** after a loading failure. Retrying does not switch
datasets, import data, or prepare query stores.

If the message says a store is not ready, prepare it in **Admin → Data**, or ask
the Web administrator. An empty result means no matching records were found;
it is different from a failed request.
