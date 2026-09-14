from ncs_backend.admin.mysql_acceptance import SMOKE_PATHS
from scripts.verify_mysql_e2e import _target


def test_acceptance_smoke_paths_cover_current_non_model_components():
    assert len(SMOKE_PATHS) == 12
    assert "/api/v1/predictions/load" not in SMOKE_PATHS
    assert "/api/v1/dashboard/manifest" in SMOKE_PATHS


def test_acceptance_target_ignores_account_identity():
    assert _target("mysql+pymysql://admin:secret@localhost:3306/ncs_analytics") == _target(
        "mysql+pymysql://reader:different@localhost/ncs_analytics"
    )
