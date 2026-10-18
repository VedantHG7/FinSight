from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from .models import RuleResult, RuleSpec


class BaseRule(ABC):

    spec: RuleSpec

    @abstractmethod
    def evaluate(
        self,
        frame: pd.DataFrame,
        index: int,
        config: dict
    ) -> RuleResult:
        pass