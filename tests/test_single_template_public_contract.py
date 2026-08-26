"""Freeze the legacy single-template render contract before MT4 adds its endpoint."""

from __future__ import annotations

import pytest

from src.service.local_client import LocalClientError, LocalDrawFlowClient
from src.service.render_service import RenderService, RenderServiceError
from src.service.v2_order_render import V2OrderRenderService
from src.service.v2_order_render_support import V2OrderRenderError


@pytest.mark.parametrize(
    "payload",
    [{}, {"template_ids": ["TEMPLATE_A", "TEMPLATE_B"]}],
    ids=["empty_request", "multi_template_parameter_cannot_replace_template_id"],
)
def test_legacy_render_services_continue_to_require_one_template_id(tmp_path, payload):
    """The new multi-template payload belongs to a new endpoint, never these APIs."""

    with pytest.raises(RenderServiceError) as generic_error:
        RenderService().submit({**payload, "order_file": str(tmp_path / "orders.xlsx")})
    with pytest.raises(LocalClientError) as local_error:
        LocalDrawFlowClient(object(), tmp_path / "local", font_dirs=[]).render(payload)
    with pytest.raises(V2OrderRenderError) as v2_error:
        V2OrderRenderService(object(), tmp_path / "v2", object(), []).render(payload)

    assert generic_error.value.code == "missing_template_id"
    assert local_error.value.code == "missing_template_id"
    assert v2_error.value.code == "missing_template_id"
