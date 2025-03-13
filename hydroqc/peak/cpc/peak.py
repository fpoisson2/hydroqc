"""Class describing a period."""

import datetime

from hydroqc.peak.basepeak import BasePeak
from hydroqc.peak.consts import DEFAULT_PRE_HEAT_DURATION
from hydroqc.peak.cpc.consts import DEFAULT_ANCHOR_DURATION, DEFAULT_ANCHOR_START_OFFSET
from hydroqc.timerange import TimeRange
from hydroqc.types import CriticalPeakDataTyping

__all__ = ["Anchor", "PreHeat", "Peak"]


class Anchor(TimeRange):
    """This class describe a period object."""

    def __init__(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        is_critical: bool = False,
    ):
        """Period constructor."""
        super().__init__(start_date, end_date, is_critical)


class PreHeat(TimeRange):
    """This class describe a period object."""

    def __init__(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        is_critical: bool = False,
    ):
        """Period constructor."""
        super().__init__(start_date, end_date, is_critical)


class Peak(BasePeak):
    """This class describe a period object."""

    # preheat: PreHeat
    # anchor: Anchor
    # _is_critical: bool

    def __init__(
        self,
        start_date: datetime.datetime,
        end_date: datetime.datetime,
        # morning_evening: str,
        preheat_duration: int = DEFAULT_PRE_HEAT_DURATION,
    ):
        """Period constructor."""
        self._preheat_duration: int = preheat_duration
        super().__init__(start_date, end_date)
        self._raw_stats: CriticalPeakDataTyping = {}

    @property
    def is_critical(self) -> bool:
        """Return True peak is critical."""
        return self._is_critical

    def set_critical(self, stats: CriticalPeakDataTyping) -> None:
        """Save critical stats in the peak and set it as critical."""
        self._is_critical = True
        self._raw_stats = stats

    @property
    def anchor(self) -> Anchor:
        """Get the anchor period of the peak."""
        anchor_start_date = self.start_date - datetime.timedelta(
            hours=DEFAULT_ANCHOR_START_OFFSET
        )
        anchor_end_date = anchor_start_date + datetime.timedelta(
            hours=DEFAULT_ANCHOR_DURATION
        )
        return Anchor(anchor_start_date, anchor_end_date, self.is_critical)

    @property
    def preheat(self) -> PreHeat:
        """Get the preheat period of the peak."""
        preheat_start_date = self.start_date - datetime.timedelta(
            minutes=self._preheat_duration
        )
        return PreHeat(preheat_start_date, self.start_date, self.is_critical)

    @property
    def credit(self) -> float | None:
        """Get credit save during this peak.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("montantEffacee")

    @property
    def ref_consumption(self) -> float | None:
        """Get reference consumption during this peak.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("consoReference")

    @property
    def actual_consumption(self) -> float | None:
        """Get actual consumption during this peak.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("consoReelle")

    @property
    def saved_consumption(self) -> float | None:
        """Get saved consumption during this peak.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("consoEffacee")

    @property
    def consumption_code(self) -> str | None:
        """Get code consumption during this peak.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("codeConso")

    @property
    def is_billed(self) -> bool | None:
        """Return True if the cpc was billed.

        Return None if the peak is not critical.
        """
        return self._raw_stats.get("indFacture")
