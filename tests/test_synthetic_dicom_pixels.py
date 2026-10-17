import numpy as np
import pydicom

from scripts.dicom.generate_synthetic_dicom import _source_image, _write_instance


def test_procedural_brain_has_visible_pixels_and_valid_window(tmp_path):
    source = _source_image()
    study = {'study_instance_uid': '1.2.826.0.1.3680043.10.54321.99.1',
             'patient_id': 'SYNTEST', 'synthetic_profile': 'ms_brain_mild'}
    series = {'series_instance_uid': study['study_instance_uid'] + '.1'}
    path = tmp_path / 'synthetic.dcm'
    _write_instance(path, source, study, series, series['series_instance_uid'] + '.1', 1)
    ds = pydicom.dcmread(path)
    pixels = ds.pixel_array
    assert pixels.shape == (256, 256)
    assert np.std(pixels) > 150
    windowed = np.clip((pixels.astype(float) - float(ds.WindowCenter)) / float(ds.WindowWidth) + .5, 0, 1)
    assert .2 < (windowed > .15).mean() < .8
    assert ds.PatientName == 'Synthetic^COHORTome'
    assert 'not a patient scan' in ds.DerivationDescription
    assert ds.file_meta.MediaStorageSOPInstanceUID == ds.SOPInstanceUID
    assert not np.array_equal(pixels, source.pixel_array)
