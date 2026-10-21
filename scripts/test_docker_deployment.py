"""Exercise a fresh synthetic Compose deployment; never use on a real runtime."""
import argparse
import time

import httpx


def wait_for(check, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    raise RuntimeError("Timed out waiting for Docker deployment")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after-restart', action='store_true')
    args = parser.parse_args()
    with httpx.Client(base_url='http://127.0.0.1:8000', timeout=180, trust_env=False) as client:
        wait_for(lambda: client.get('/auth/me').status_code == 200)
        login = client.post('/auth/login', json={'username': 'smoke', 'password': 'synthetic-test-only'})
        login.raise_for_status()
        assert client.get('/auth/me').json()['enabled'] is True
        wait_for(lambda: client.get('/jobs/status').json().get('available'))
        if args.after_restart:
            assert client.get('/user-settings').json()['appearance'] == 'dark'
            print('PASS: authentication, worker and settings survive restart')
            return
        for dataset in ('default', 'synthetic-cross-sectional-demo'):
            client.post(f'/datasets/{dataset}/prepare-store').raise_for_status()
            response = client.get('/query', params={'q': 'List all patients', 'dataset_id': dataset})
            response.raise_for_status()
            assert response.json()['data']['patient_count'] > 0
        client.patch('/user-settings', json={'appearance': 'dark'}).raise_for_status()
        response = client.get('/pheno-ranker/patient-ids', params={'dataset_id': 'default'})
        response.raise_for_status()
        selected = response.json()['record_ids'][:3]
        assert len(selected) == 3
        response = client.post('/pheno-ranker/run', json={
            'dataset_id': 'default', 'mode': 'cohort', 'include_terms': ['diseases'],
            'selected_patient_ids': ','.join(selected), 'similarity_metric_cohort': 'jaccard',
        })
        response.raise_for_status()
        result = response.json()
        assert result['returncode'] == 0, result.get('stderr')
        files = {item['name']: item['url'] for item in result['files']}
        for name in ('matrix.txt', 'graph.json', 'mds_points.tsv'):
            artifact = client.get(files[name])
            artifact.raise_for_status()
            assert artifact.content, name
        print('PASS: real Pheno-Ranker comparison, graph and MDS artifacts')
        response = client.post('/analysis', json={
            'dataset_id': 'default', 'prompt': 'Summarize the synthetic clinical cohort',
            'catalog_item_id': 'external-r-clinical-profile',
        })
        response.raise_for_status()
        job_id = response.json()['data']['job_id']

        def completed():
            response = client.get(f'/jobs/{job_id}')
            response.raise_for_status()
            job = response.json()
            if job['status'] in ('failed', 'cancelled'):
                raise RuntimeError(f"Queued R analysis failed: {job.get('error', '')}")
            return job['status'] == 'completed' and job['result_available']

        wait_for(completed, timeout=300)
        print('PASS: authenticated queries for both demos and real queued R analysis')


if __name__ == '__main__':
    main()
