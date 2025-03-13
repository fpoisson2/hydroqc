"""CPC processing."""

import datetime
import logging

from hydroqc import utils
from hydroqc.error import HydroQcCPCPeakError
from hydroqc.hydro_api.client import HydroClient
from hydroqc.peak.basepeakhandler import BasePeakHandler
from hydroqc.peak.cpc.consts import (
    DEFAULT_EVENING_PEAK_END,
    DEFAULT_EVENING_PEAK_START,
    DEFAULT_MORNING_PEAK_END,
    DEFAULT_MORNING_PEAK_START,
    MORNING_EVENING,
)
from hydroqc.peak.cpc.peak import Anchor, Peak
from hydroqc.types import CPCDataTyping, CriticalPeakDataTyping, OpenDataPeakEventOffer
from hydroqc.utils import EST_TIMEZONE


def _get_peak_date(
    peak_date: datetime.datetime, start_end: str, morning_evening: str
) -> datetime.datetime:
    """Get the start date of the peak."""
    default_dates = {
        "morning": {
            "start": DEFAULT_MORNING_PEAK_START,
            "end": DEFAULT_MORNING_PEAK_END,
        },
        "evening": {
            "start": DEFAULT_EVENING_PEAK_START,
            "end": DEFAULT_EVENING_PEAK_END,
        },
    }
    if start_end not in ("start", "end"):
        msg = f"Peak date type {start_end} needs be one of ('start', 'end')"
        raise HydroQcCPCPeakError(msg)
    if morning_evening not in ("morning", "evening"):
        msg = f"Peak type {morning_evening} needs be one of {MORNING_EVENING}"
        raise HydroQcCPCPeakError(msg)
    event_date = peak_date.replace(
        hour=default_dates[morning_evening][start_end].hour,
        minute=default_dates[morning_evening][start_end].minute,
        second=default_dates[morning_evening][start_end].second,
    )
    if not event_date.tzinfo:
        event_date = event_date.astimezone(EST_TIMEZONE)
    return event_date


class CPCPeakHandler(BasePeakHandler[Peak]):
    """CPC extra logic.

    This class supplements Hydro API data by providing calculated values for pre_heat period,
    anchor period detection as well as next event information.
    """

    _offer_code: OpenDataPeakEventOffer = "CPC-D"

    def __init__(
        self,
        applicant_id: str,
        customer_id: str,
        contract_id: str,
        hydro_client: HydroClient,
        logger: logging.Logger,
    ):
        """CPC constructor."""
        super().__init__(
            applicant_id,
            customer_id,
            contract_id,
            hydro_client,
            logger,
        )

        self._raw_data: CPCDataTyping = {}

    # Fetch raw data
    async def refresh_data(self) -> None:
        """Get data from HydroQuebec web site."""
        self._logger.debug("Fetching data from HydroQuebec...")
        self._raw_data = await self._hydro_client.get_cpc_credit(
            self.applicant_id, self.customer_id, self.contract_id
        )
        self._logger.debug("Data fetched from HydroQuebec...")
        # Ensure that peaks are sorted by date
        if self._raw_data["periodesEffacementsHivers"]:
            self._raw_data["periodesEffacementsHivers"][0][
                "periodesEffacementHiver"
            ].sort(key=lambda x: (x["dateEffacement"], x["heureDebut"]))

    @property
    def raw_data(self) -> CPCDataTyping:
        """Return raw collected data."""
        return self._raw_data

    # Internals
    @property
    def _raw_critical_peaks(self) -> list[CriticalPeakDataTyping]:
        """Shortcut to get quickly critical peaks."""
        if self._raw_data.get("periodesEffacementsHivers"):
            return self._raw_data["periodesEffacementsHivers"][0][
                "periodesEffacementHiver"
            ]
        return []

    def _set_peak_critical(self, peak: Peak) -> None:
        """Determine if the passed peak is critical or not, and save it to the object."""
        if peak.morning_evening.upper() == "EVENING":
            default_start_time_str = DEFAULT_EVENING_PEAK_START.strftime("%H:%M:%S")
        elif peak.morning_evening.upper() == "MORNING":
            default_start_time_str = DEFAULT_MORNING_PEAK_START.strftime("%H:%M:%S")
        else:
            raise HydroQcCPCPeakError("Bad morning_evening value")

        for open_critical_peak in self.raw_open_data:
            critical_peak_enddate = datetime.datetime.fromisoformat(
                open_critical_peak["dateFin"]
            )
            # TODO which want do we want ?
            # if critical_peak_startdate > utils.now() \
            # and critical_peak_startdate == peak.start_date:
            if critical_peak_enddate == peak.end_date:
                raw_stats: CriticalPeakDataTyping = {}
                peak.set_critical(raw_stats)
                break

        for critical_peak in self._raw_critical_peaks:
            critical_peak_date = datetime.datetime.strptime(
                critical_peak["dateEffacement"], "%Y-%m-%dT%H:%M:%S.%f%z"
            ).date()
            if (
                critical_peak_date == peak.day
                and critical_peak["heureDebut"] == default_start_time_str
            ):
                raw_stats = critical_peak.copy()
                peak.set_critical(raw_stats)
                return

    # general data
    @property
    def winter_start_date(self) -> datetime.datetime:
        """Get start date of the cpc peaks period."""
        if not self._raw_data.get("periodesEffacementsHivers"):
            return super().winter_start_date
        return datetime.datetime.strptime(
            self._raw_data["periodesEffacementsHivers"][0]["dateDebutPeriodeHiver"],
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ).astimezone(EST_TIMEZONE)

    @property
    def winter_end_date(self) -> datetime.datetime:
        """Get end date of the cpc peaks period."""
        if not self._raw_data.get("periodesEffacementsHivers"):
            return super().winter_end_date
        return datetime.datetime.strptime(
            self._raw_data["periodesEffacementsHivers"][0]["dateFinPeriodeHiver"],
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ).astimezone(EST_TIMEZONE)

    @property
    def cumulated_credit(self) -> float:
        """Get cumulated credits."""
        return round(sum(p["montantEffacee"] for p in self._raw_critical_peaks), 2)

    @property
    def cumulated_critical_hours(self) -> float:
        """Get total number of hours as critical peak."""
        total = sum(
            [
                datetime.datetime.strptime(p["heureFin"], "%H:%M:%S")
                - datetime.datetime.strptime(p["heureDebut"], "%H:%M:%S")
                for p in self._raw_critical_peaks
            ],
            datetime.timedelta(),
        )
        return total.total_seconds() / 3600

    @property
    def cumulated_curtailed_energy(self) -> float:
        """Get total number of curtailed energy in kWh."""
        return sum(p["consoEffacee"] for p in self._raw_critical_peaks)

    @property
    def projected_cumulated_credit(self) -> float:
        """Get projected_cumulated credits."""
        if self._raw_data["montantEffaceProjete"] == "":
            return 0.0
        try:
            return float(self._raw_data["montantEffaceProjete"])
        except ValueError as exp:
            raise HydroQcCPCPeakError("Bad cumulated credit raw value") from exp

    # Peaks data
    def _get_peaks(self) -> list[Peak]:
        """Get all peaks of the current winter."""
        current_date = self.winter_start_date
        delta = datetime.timedelta(days=1)
        peak_list: list[Peak] = []
        while current_date.date() <= self.winter_end_date.date():
            # Morning
            peak = Peak(
                start_date=_get_peak_date(current_date, "start", "morning"),
                end_date=_get_peak_date(current_date, "end", "morning"),
                preheat_duration=self._preheat_duration,
            )
            self._set_peak_critical(peak)
            peak_list.append(peak)
            # Evening
            peak = Peak(
                start_date=_get_peak_date(current_date, "start", "evening"),
                end_date=_get_peak_date(current_date, "end", "evening"),
                preheat_duration=self._preheat_duration,
            )
            self._set_peak_critical(peak)
            peak_list.append(peak)
            # Next day
            current_date += delta
        peak_list.sort(key=lambda x: x.start_date)
        return peak_list

    @property
    def critical_peaks(self) -> list[Peak]:
        """Get all critical peaks of the current credits."""
        return [p for p in self.peaks if p.is_critical]

    # Current peak
    @property
    def current_peak_is_critical(self) -> bool | None:
        """Return True if the current peak is critical."""
        if self.current_peak:
            return bool(self.current_peak.is_critical)
        return None

    # In progress
    @property
    def current_state(self) -> str:
        """Get the current state of the cpc handler.

        It returns critical_anchor, anchor, critical_peak, peak or normal
        This value should help for automation.
        """
        now = utils.now()
        current_anchors = [
            p.anchor
            for p in self.peaks
            if p.anchor.start_date < now < p.anchor.end_date
        ]
        if current_anchors and current_anchors[0].is_critical:
            return "critical_anchor"
        if current_anchors and not current_anchors[0].is_critical:
            return "anchor"

        current_peaks = [p for p in self.peaks if p.start_date < now < p.end_date]
        if current_peaks and current_peaks[0].is_critical:
            return "critical_peak"
        if current_peaks and not current_peaks[0].is_critical:
            return "peak"
        return "normal"

    @property
    def next_peak(self) -> Peak | None:
        """Get next peak or current peak."""
        return self._get_next_peak()

    # Upcoming
    @property
    def is_any_critical_peak_coming(self) -> bool:
        """Get critical state of the upcoming events.

        It will return True if one of the "not completed yet" peak is critical.

        Retourne True si au moins un des prochains peaks non terminés est critical.
        """
        return bool(self.next_critical_peak)

    # Next peak
    @property
    def next_peak_is_critical(self) -> bool:
        """Return True if the following next peak is critical.

        This method is quite useless because, to call this attribute

        * we need to write::

            contract.peak_handler.next_peak_is_critical

        * but it equivalent to::

            contract.peak_handler.next_peak.is_critical

        """
        if (next_peak := self._get_next_peak()) is None:
            return False
        return next_peak.is_critical

    @property
    def next_critical_peak(self) -> Peak | None:
        """Get next peak or current peak."""
        now = utils.now()
        peaks: list[Peak] = [p for p in self.critical_peaks if now < p.end_date]
        if not peaks:  # pylint: disable=consider-using-assignment-expr
            return None
        next_peak = min(peaks, key=lambda x: x.start_date)
        return next_peak

    # Yesterday peaks
    @property
    def yesterday_morning_peak(self) -> Peak | None:
        """Get the peak of yesterday morning."""
        now = utils.now()
        peaks: list[Peak] = [
            p
            for p in self.peaks
            if p.day == now.date() - datetime.timedelta(days=1) and p.is_morning
        ]
        if len(peaks) > 1:
            raise HydroQcCPCPeakError("There is more than one morning peak yesterday !")
        if len(peaks) == 1:
            return peaks[0]
        return None

    @property
    def yesterday_evening_peak(self) -> Peak | None:
        """Get the peak of yesterday evening."""
        now = utils.now()
        peaks: list[Peak] = [
            p
            for p in self.peaks
            if p.day == now.date() - datetime.timedelta(days=1) and p.is_evening
        ]
        if len(peaks) > 1:
            raise HydroQcCPCPeakError("There is more than one evening peak yesterday !")
        if len(peaks) == 1:
            return peaks[0]
        return None

    # Anchors
    @property
    def next_anchor(self) -> Anchor | None:
        """Next or current anchor."""
        now = utils.now()
        anchors: list[Anchor] = [
            p.anchor for p in self.peaks if now < p.anchor.end_date
        ]
        if anchors:
            next_anchor: Anchor = min(anchors, key=lambda x: x.start_date)
            return next_anchor
        return None
