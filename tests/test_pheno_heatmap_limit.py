import subprocess
from pathlib import Path


def test_heatmap_limit_counts_records_not_patients():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(['node', '--input-type=module', '-e', r'''
      import assert from 'node:assert/strict';
      import {phenoHeatmapRecordCount as count, PHENO_HEATMAP_MAX_RECORDS as limit} from './static/js/pheno.js';
      const matrix = n => '\t' + Array.from({length:n}, (_,i)=>'record'+i).join('\t') + '\r\n';
      assert.equal(limit, 1000);
      assert.equal(count(''), 0);
      assert.equal(count(matrix(1000)), 1000);
      assert.equal(count(matrix(1001)), 1001);
      assert.ok(count(matrix(1000)) <= limit);
      assert.ok(count(matrix(1001)) > limit);
      assert.equal(count('id\ta\n' + 'row\t0\n'.repeat(1001)), 1001);
    '''], cwd=root, check=True, capture_output=True, text=True)
