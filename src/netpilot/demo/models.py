from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from netpilot.environment import EnvironmentUpdate


class DemoScenarioStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    order: int = Field(ge=1)
    actor: Literal["user", "system", "fixture"]
    action: str
    expected_state: dict[str, Any] = Field(default_factory=dict)


class DemoScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    title: str
    description: str
    target_mode: Literal["remote_user_client"] = "remote_user_client"
    environment_fixture: EnvironmentUpdate
    snapshot_fixtures: tuple[str, ...]
    expected_initial_issue: str
    expected_remediation_templates: tuple[str, ...]
    expected_verification_result: str | None = None
    expected_resolution_state: str | None = None
    supports_escalation: bool = False
    recommended_input: str
    steps: tuple[DemoScenarioStep, ...]


class DemoSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = "dns_recovery"
