"""Pure browser-module checks without a frontend build dependency."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_assay_display_labels_are_shared():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for JavaScript module checks")
    module = Path("static/js/assay_labels.js").resolve().as_uri()
    script = f"""
      import assert from 'node:assert/strict';
      import {{ formatAssayModality as modality, formatAssayDataType as dataType,
        formatAssayRequirementLabel as requirement }} from {module!r};
      for (const [id, label] of Object.entries({{
        methylation: 'DNA methylation', flow_cytometry: 'Immune-cell abundance',
        imaging: 'Imaging', olink: 'OLINK', serology: 'Serology'
      }})) {{
        assert.equal(modality(id), label);
        assert.equal(requirement(id), label);
      }}
      for (const id of ['raw_counts', 'm_values', 'allele_dosage', 'dicom_derived_measurements']) {{
        assert.equal(dataType(id), requirement(id));
      }}
      assert.equal(requirement(' DNA_CUSTOM-panel '), 'Dna Custom Panel');
      assert.equal(requirement(null), '');
      assert.equal(modality('custom_assay'), 'Custom Assay');
      assert.equal(dataType('custom_matrix'), 'Custom Matrix');
    """
    subprocess.run([node, "--input-type=module", "-e", script], check=True, capture_output=True, text=True)
