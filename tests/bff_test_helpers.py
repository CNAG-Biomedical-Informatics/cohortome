import json
from types import SimpleNamespace
import app.auth as auth_module
import app.jobs as jobs_module
import app.lm as lm_module
import app.query_store as query_store_module
import app.user_state as user_state_module


def write_json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def isolate_auth_store(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_module, "AUTH_USERS_PATH", tmp_path / "state" / "auth" / "users.json")
    monkeypatch.setattr(auth_module, "PASSWORD_RESET_TOKENS_PATH", tmp_path / "state" / "auth" / "password-reset-tokens.json")


def isolate_user_state(monkeypatch, tmp_path):
    monkeypatch.setattr(user_state_module, "STATE_ROOT_DIR", tmp_path / "state")


def isolate_query_store(monkeypatch, tmp_path):
    monkeypatch.setattr(query_store_module, "QUERY_STORE_DIR", tmp_path / "state" / "query-store")


def isolate_jobs_store(monkeypatch, tmp_path):
    monkeypatch.setattr(
        jobs_module,
        "user_state_dir",
        lambda user_id=None: tmp_path / "state" / "users" / user_state_module.normalize_user_id(user_id),
    )


def isolate_lm_provider_store(monkeypatch, tmp_path):
    monkeypatch.setattr(lm_module, "LLM_PROVIDER_REGISTRY_PATH", tmp_path / "state" / "llm" / "providers.json")


def make_request(session=None):
    return SimpleNamespace(session=session or {})


def _write_synthetic_methylation_runner_fixture(tmp_path):
    assay_dir = tmp_path / "assays" / "methylation"
    assay_dir.mkdir(parents=True)
    sample_ids = ["METH001", "METH002", "METH003", "METH004", "METH005", "METH006"]
    write_json(
        tmp_path,
        "records.json",
        [{"id": sample_id, "patient_id": sample_id} for sample_id in sample_ids],
    )
    matrix_path = assay_dir / "synthetic_m_values.csv"
    matrix_path.write_text(
        "feature_id;" + ";".join(sample_ids) + "\n"
        "cg00000001;2.2;2.0;2.4;-1.8;-2.0;-1.7\n"
        "cg00000002;1.4;1.2;1.5;-1.1;-1.3;-1.0\n"
        "cg00000003;-2.1;-1.9;-2.2;1.7;1.9;1.6\n"
        "cg00000004;0.3;0.2;0.4;0.1;0.0;0.2\n"
        "cg00000005;1.0;0.8;1.1;0.9;0.7;1.0\n"
        "cg00000006;-0.5;-0.7;-0.4;-0.6;-0.8;-0.5\n",
        encoding="utf-8",
    )
    metadata_path = assay_dir / "sample_metadata.csv"
    metadata_path.write_text(
        "sample_id;patient_id;age;plate\n"
        "METH001;METH001;41;101\n"
        "METH002;METH002;47;102\n"
        "METH003;METH003;53;101\n"
        "METH004;METH004;43;102\n"
        "METH005;METH005;49;101\n"
        "METH006;METH006;55;102\n",
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_methylation_m_values",
                        "modality": "methylation",
                        "data_type": "m_values",
                        "feature_namespace": "illumina_cpg_probe_id",
                        "file": "assays/methylation/synthetic_m_values.csv",
                        "sample_metadata_file": "assays/methylation/sample_metadata.csv",
                        "analysis_covariates": ["age", "plate"],
                        "analysis_covariate_types": {"age": "numeric", "plate": "categorical"},
                        "feature_count": 6,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return matrix_path


def _write_synthetic_quantitative_assay_runner_fixture(tmp_path):
    write_json(
        tmp_path,
        "records.json",
        [{"id": f"SYN00{index}"} for index in range(1, 7)],
    )
    assay_dir = tmp_path / "assays" / "serology"
    assay_dir.mkdir(parents=True)
    matrix_path = assay_dir / "synthetic_quantitative_serology.tsv"
    matrix_path.write_text(
        "feature_id\tSYN001\tSYN002\tSYN003\tSYN004\tSYN005\tSYN006\n"
        "Marker_up\t8\t9\t10\t1\t2\t3\n"
        "Marker_constant\t5\t5\t5\t5\t5\t5\n"
        "Marker_sparse\tNA\tNA\t4\t1\t2\t3\n",
        encoding="utf-8",
    )
    metadata_path = assay_dir / "sample_metadata.tsv"
    metadata_path.write_text(
        "sample_id\tpatient_id\n"
        + "".join(f"SYN00{index}\tSYN00{index}\n" for index in range(1, 7)),
        encoding="utf-8",
    )
    (tmp_path / "assays" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "assays": [
                    {
                        "assay_id": "synthetic_quantitative_serology",
                        "label": "Synthetic quantitative serology",
                        "modality": "serology",
                        "data_type": "quantitative_measurement",
                        "feature_count": 3,
                        "file": "assays/serology/synthetic_quantitative_serology.tsv",
                        "sample_metadata_file": "assays/serology/sample_metadata.tsv",
                        "patient_linkage": "sample_metadata_file",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return matrix_path
