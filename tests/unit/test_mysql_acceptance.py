from ncs_backend.admin.mysql_acceptance import SMOKE_PATHS


def test_acceptance_smoke_paths_cover_current_non_model_components():
    assert len(SMOKE_PATHS) == 12
    assert "/api/v1/predictions/load" not in SMOKE_PATHS
    assert "/api/v1/dashboard/manifest" in SMOKE_PATHS
