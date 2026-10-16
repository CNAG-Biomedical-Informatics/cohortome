from app.analysis_resources import THREAD_ENV, single_thread_environment


def test_analysis_threads_override_inherited_limits_without_mutating_parent(monkeypatch):
    import os
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "12")
    monkeypatch.setenv("OMP_NUM_THREADS", "8")
    monkeypatch.setenv("PERL5LIB", "/example/perl/lib")
    env = single_thread_environment()
    assert all(env[key] == "1" for key in THREAD_ENV)
    assert env["PERL5LIB"] == "/example/perl/lib"
    assert os.environ["OPENBLAS_NUM_THREADS"] == "12"
    assert os.environ["OMP_NUM_THREADS"] == "8"
