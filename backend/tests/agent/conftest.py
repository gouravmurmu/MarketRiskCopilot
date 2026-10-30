from datetime import date
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from riskcopilot.config import Settings
from riskcopilot.db import models as m
from riskcopilot.db import repo
from riskcopilot.db.session import make_engine, make_session_factory
from riskcopilot.jobs.eod import run_eod
from tests.conftest import FakePrices, synthetic_prices

AS_OF = date(2020, 1, 31)


@pytest.fixture(scope="package")
def factory(tmp_path_factory):
    engine = make_engine(f"sqlite:///{tmp_path_factory.mktemp('agent') / 'agent.db'}")
    m.Base.metadata.create_all(engine)
    f = make_session_factory(engine)
    settings = Settings(history_start="2018-01-01", mc_paths=2_000)
    assert run_eod(f, FakePrices(synthetic_prices()), None, settings, AS_OF).status == "ok"
    dates = pd.bdate_range("2019-12-01", AS_OF)
    rng = np.random.default_rng(1)
    macro = pd.DataFrame(
        {
            "DGS10": 1.8 + rng.normal(0, 0.03, len(dates)).cumsum(),
            "VIXCLS": 14 + rng.normal(0, 0.5, len(dates)).cumsum(),
        },
        index=dates,
    )
    with f.begin() as s:
        repo.write_macro(s, macro)
    return f


@pytest.fixture
def settings() -> Settings:
    return Settings(anthropic_api_key="test-key", agent_max_retries=2)


def response(text: str = "", tool_uses: list[dict[str, Any]] | None = None, stop: str = "") -> Any:
    content: list[Any] = []
    if text:
        content.append(SimpleNamespace(type="text", text=text))
    for u in tool_uses or []:
        content.append(SimpleNamespace(type="tool_use", **u))
    stop = stop or ("tool_use" if tool_uses else "end_turn")
    return SimpleNamespace(
        content=content,
        stop_reason=stop,
        model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


class FakeStream:
    def __init__(self, resp: Any) -> None:
        self.resp = resp

    def __enter__(self) -> "FakeStream":
        return self

    def __exit__(self, *a: Any) -> None:
        return None

    def __iter__(self):
        for b in self.resp.content:
            if b.type == "text":
                yield SimpleNamespace(type="text", text=b.text)

    def get_final_message(self) -> Any:
        return self.resp


class FakeClient:
    """Stands in for anthropic.Anthropic: replays canned responses and records requests."""

    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(
            messages=SimpleNamespace(create=self._create, stream=self._stream)
        )

    def _create(self, **kw: Any) -> Any:
        self.requests.append(kw)
        return self.responses.pop(0)

    def _stream(self, **kw: Any) -> FakeStream:
        self.requests.append(kw)
        return FakeStream(self.responses.pop(0))
