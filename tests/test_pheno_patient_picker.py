import subprocess
from pathlib import Path


def test_readable_picker_keeps_dataset_scoped_execution_keys():
    subprocess.run(['node', '--input-type=module', '-e', r'''
      import assert from 'node:assert/strict';
      import {identityKey} from './static/js/identities.js';
      import {createPhenoPatientPicker} from './static/js/pheno_patient_picker.js';
      globalThis.document = {createElement: () => ({value:''})};
      const input = {value:''};
      const choices = {replaceChildren(...items) { this.items = items; }};
      const picker = createPhenoPatientPicker(input, choices);
      const a = identityKey('study-a', 'patient', 'P01');
      const b = identityKey('study-b', 'patient', 'P01');
      const visit = identityKey('study-a', 'sample', 'P01');
      // Restoring a saved setup before the async roster arrives must retain its key.
      picker.set(b);
      assert.equal(input.value, 'study-b · P01');
      assert.equal(picker.get(), b);
      picker.load([a,b], [visit]);
      assert.equal(picker.get(), b);
      assert.ok(choices.items.every(o => !o.value.includes('cohortome-v1-')));
      input.value = 'study-a · P01 (patient)';
      assert.equal(picker.get(), a);
      input.value = 'study-a · P01 (visit)';
      assert.equal(picker.get(), visit);
      input.value = 'study-b · P01';
      assert.equal(picker.get(), b);
      input.value = a;
      assert.equal(picker.get(), a);
      picker.set(visit);
      assert.equal(input.value, 'study-a · P01 (visit)');
      picker.reset();
      assert.equal(picker.get(), '');
      assert.equal(choices.items.length, 0);
      picker.load(['plain-id'], []);
      input.value = 'plain-id';
      assert.equal(picker.get(), 'plain-id');
      input.value = 'unknown';
      assert.equal(picker.get(), 'unknown'); // existing validation rejects this
    '''], cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True)
