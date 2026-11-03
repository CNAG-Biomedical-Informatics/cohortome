import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {modalityKey, modalityLabel, modalityPresentation, modalityIcon, mountModalityIcons} from '../static/js/modalities.js';

const theme = readFileSync(new URL('../static/css/theme.css', import.meta.url), 'utf8');
for (const key of ['clinical', 'assay', 'transcriptomics', 'methylation', 'proteomics', 'flow_cytometry', 'serology', 'genotyping', 'imaging']) {
  const presentation = modalityPresentation(key);
  assert.equal(presentation.label, modalityLabel(key));
  assert(modalityIcon(key).includes(presentation.icon));
  assert(modalityIcon(key).includes(presentation.color));
  assert(theme.includes(presentation.darkColor));
  assert(!presentation.icon.includes('<script'));
}
assert.equal(modalityKey('olink'), 'proteomics');
assert.equal(modalityLabel('olink'), 'OLINK');
assert.equal(modalityKey('dicom'), 'imaging');
assert.equal(modalityKey('variants'), 'genotyping');
assert.equal(modalityKey('metabolomics'), 'assay');
assert(!modalityIcon('<img src=x onerror=alert(1)>').includes('<img'));
const element = {dataset: {modalitySymbol: 'clinical'}, innerHTML: ''};
mountModalityIcons({querySelectorAll: () => [element]});
assert.equal(element.innerHTML, modalityIcon('clinical', ''));
const docs = readFileSync(new URL('../docs-site/src/components/ModalityTable/index.tsx', import.meta.url), 'utf8');
assert(docs.includes("from '../../../../static/js/modalities.js'"));
assert(!docs.includes('<path') && !docs.includes('#6d28d9'));
console.log('Shared modality icons, theme colours, aliases and docs linkage passed.');
