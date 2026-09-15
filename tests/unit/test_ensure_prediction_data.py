from scripts import ensure_prediction_data


def test_existing_prediction_skips_model_loading(monkeypatch):
    monkeypatch.setattr(ensure_prediction_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_prediction_data, "_published_load_batch", lambda url: "batch-1")
    monkeypatch.setattr(ensure_prediction_data, "_prediction_ready", lambda url, batch: True)
    monkeypatch.setattr(
        ensure_prediction_data,
        "_newest_model",
        lambda: (_ for _ in ()).throw(AssertionError("must not load model")),
    )

    assert ensure_prediction_data.main() == 0


def test_missing_model_is_optional(monkeypatch):
    monkeypatch.setattr(ensure_prediction_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_prediction_data, "_published_load_batch", lambda url: "batch-1")
    monkeypatch.setattr(ensure_prediction_data, "_prediction_ready", lambda url, batch: False)
    monkeypatch.setattr(ensure_prediction_data, "_newest_model", lambda: None)

    assert ensure_prediction_data.main() == ensure_prediction_data.NO_MODEL_EXIT


def test_missing_load_hourly_stops_prediction(monkeypatch):
    monkeypatch.setattr(ensure_prediction_data, "load_local_config", lambda path: None)
    monkeypatch.setenv("NCS_DATABASE_URL", "mysql+pymysql://root@vm/db")
    monkeypatch.setattr(ensure_prediction_data, "_published_load_batch", lambda url: None)

    assert ensure_prediction_data.main() == 4
