"""Test local-file rendering with the desktop backend and Linux system WebKitGTK.

Uses only synthetic files and a disposable runtime. Requires python3-gi and
gir1.2-webkit2-4.1, plus the normal source-app Python dependencies.
"""
import json
import base64
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import pydicom

ROOT = Path(__file__).resolve().parents[2]


def main():
    sys.path.append('/usr/lib/python3/dist-packages')
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('WebKit2', '4.1')
    from gi.repository import Gtk, WebKit2, GLib

    with tempfile.TemporaryDirectory(prefix='cohortome-dicom-native-') as temporary:
        work = Path(temporary)
        images = work / 'images'
        images.mkdir()
        source = next((ROOT / 'datasets/synthetic-longitudinal-demo/assays/imaging/dicom').glob('*.dcm'))
        ds = pydicom.dcmread(source)
        study = str(ds.StudyInstanceUID)
        for index in range(12):
            ds.SOPInstanceUID = study + '.77.' + str(index + 1)
            ds.file_meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
            ds.SeriesInstanceUID = study + '.77'
            ds.InstanceNumber = index + 1
            ds.ImagePositionPatient = [0, 0, float(index)]
            ds.save_as(images / f'slice-{index + 1:02}.dcm')
        env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / '.deps'), str(ROOT)]))
        server = subprocess.Popen([sys.executable, str(ROOT / 'desktop/server.py'),
                                   '--runtime-dir', str(work / 'runtime')], cwd=ROOT, env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            ready = json.loads(server.stdout.readline())
            window = Gtk.Window(title='COHORTome — synthetic desktop viewer test')
            window.set_default_size(1200, 850)
            view = WebKit2.WebView()
            window.add(view)
            state = {'started': False, 'passed': False, 'checks': 0}
            def loaded(_view, event):
                if event != WebKit2.LoadEvent.FINISHED or state['started'] or '/desktop/open' in view.get_uri():
                    return
                state['started'] = True
                script = '''(async () => {
                  const r = await fetch('/local-viewer/datasets/default/folder', {
                    method:'POST', headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({directory:DIR})});
                  if (!r.ok) {document.body.textContent='LINK FAILED '+await r.text(); return;}
                  location.href='/local-viewer/open/default/STUDY';
                })();'''.replace('DIR', json.dumps(str(images))).replace('STUDY', study)
                view.evaluate_javascript(script, -1, None, None, None, None, None)
            view.connect('load-changed', loaded)
            def measured(widget, result, _):
                try:
                    value = json.loads(widget.evaluate_javascript_finish(result).to_string())
                    if value and value['nonblack'] > .05 and value['stddev'] > 5 and value['width'] > 300:
                        state['passed'] = True
                        Path('/tmp/cohortome-dicom-native.png').write_bytes(base64.b64decode(value.pop('png').split(',', 1)[1]))
                        print('PASS: desktop backend, 12 linked DICOM instances, native WebKit pixels', value, flush=True)
                        Gtk.main_quit()
                except Exception:
                    pass
            def inspect():
                state['checks'] += 1
                if state['checks'] > 60:
                    Gtk.main_quit()
                    return False
                script = '''JSON.stringify((() => {
                  const c=[...document.querySelectorAll('canvas')].sort((a,b)=>b.width*b.height-a.width*a.height)[0];
                  if(!c) return null;
                  const ctx=c.getContext('2d'); if(!ctx) return null;
                  const d=ctx.getImageData(0,0,c.width,c.height).data;
                  let n=0,sum=0,sq=0;for(let i=0;i<d.length;i+=4) {
                    const v=(d[i]+d[i+1]+d[i+2])/3; if(v>8)n++;sum+=v;sq+=v*v;
                  }
                  const count=c.width*c.height;
                  return {width:c.width,height:c.height,nonblack:n/count,stddev:Math.sqrt(sq/count-(sum/count)**2),png:c.toDataURL()};
                })())'''
                view.evaluate_javascript(script, -1, None, None, None, measured, None)
                return True
            GLib.timeout_add(1000, inspect)
            view.load_uri(ready['url'])
            window.show_all()
            Gtk.main()
            window.destroy()
            if not state['passed']:
                raise RuntimeError('Native viewer did not render a non-black main canvas within 60 seconds.')
        finally:
            server.stdin.close()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.terminate()
                server.wait(timeout=10)


if __name__ == '__main__':
    main()
