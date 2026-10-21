import { displayIdentity } from './identities.js';

// Visible labels are not execution keys; retain the key when restoring a chat.
export function createPhenoPatientPicker(input, choices) {
  let options = [], savedKey = '', savedLabel = '';
  function get() {
    const value = input?.value.trim() || '';
    if (!value) return '';
    if (value === savedLabel) return savedKey;
    if (options.some(o => o.key === value)) return value;
    const matches = options.filter(o => o.label === value);
    return matches.length === 1 ? matches[0].key : value;
  }
  function set(key) {
    savedKey = String(key || '').trim();
    savedLabel = options.find(o => o.key === savedKey)?.label || displayIdentity(savedKey);
    if (input) input.value = savedLabel;
  }
  function load(patientIds, recordIds) {
    const current = get();
    const ids = [...new Set([...recordIds, ...patientIds])];
    const labels = ids.map(id => displayIdentity(id));
    options = ids.map((key, i) => ({key, label: labels[i] + (labels.indexOf(labels[i]) !== labels.lastIndexOf(labels[i])
      ? (recordIds.includes(key) ? ' (visit)' : ' (patient)') : '')}));
    if (choices) choices.replaceChildren(...options.map(({label}) => {
      const option = document.createElement('option');
      option.value = label;
      return option;
    }));
    set(current);
  }
  function reset() {
    options = []; savedKey = ''; savedLabel = '';
    if (input) input.value = '';
    choices?.replaceChildren();
  }
  return {get, set, load, reset};
}
