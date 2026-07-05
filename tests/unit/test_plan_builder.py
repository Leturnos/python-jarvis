import pytest

from core.execution.plan_builder import PlanBuilder
from core.shared.errors import BusinessError


def test_plan_builder_warp_missing_path():
    config = {"integrations": {"warp": {"path": ""}}}
    builder = PlanBuilder(config)
    with pytest.raises(BusinessError) as exc_info:
        builder.build_warp_plan({"commands": ["ls"]})
    assert "Caminho do terminal Warp não está configurado" in str(exc_info.value)
