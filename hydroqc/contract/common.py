"""Hydroquebec contract module."""

import functools
import logging
from abc import ABC
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from io import StringIO
from typing import ParamSpec, TypeVar, cast

from hydroqc.contract.outage import Outage
from hydroqc.hydro_api.client import HydroClient
from hydroqc.logger import get_logger
from hydroqc.types import (
    ConsumpAnnualTyping,
    ConsumpDailyTyping,
    ConsumpHourlyTyping,
    ConsumpMonthlyTyping,
    ContractTyping,
    OutageListTyping,
    PeriodDataTyping,
)
from hydroqc.utils import EST_TIMEZONE

T = TypeVar("T")
P = ParamSpec("P")


def check_period_data_present(
    method: Callable[..., None | str | bool | float | PeriodDataTyping],
) -> Callable[..., None | str | bool | float | PeriodDataTyping]:
    """Check if contract's data are present."""

    def wrapper(contract: "Contract") -> None | str | bool | float | PeriodDataTyping:
        if not hasattr(contract, "_all_period_data"):
            contract._logger.warning("You need to call get_period_info method first")
            return None
        if not contract._all_period_data:
            contract._logger.info(
                "It seems Hydro-Québec didn't provided some data. "
                "Maybe you did a rate change recently. "
                "This message should disappear at the beginning of the next bill period."
            )
        return method(contract)

    return wrapper


def check_info_data_present(
    method: Callable[..., None | str | bool | float | date],
) -> Callable[..., None | str | bool | float | date]:
    """Check if contract's data are present."""

    def wrapper(contract: "Contract") -> None | str | bool | float | date:
        if not hasattr(contract, "_raw_info_data"):
            contract._logger.warning("You need to call get_info method first")
            return None
        if not contract._raw_info_data:
            contract._logger.info(
                "It seems Hydro-Québec didn't provided some data. "
                "Maybe you did a rate change recently. "
                "This message should disappear at the beginning of the next bill period."
            )
        return method(contract)

    return wrapper


def check_annual_data_present(
    method: Callable[..., None | str | bool | float | date],
) -> Callable[..., None | str | bool | float | date]:
    """Check if contract's data are present."""

    def wrapper(contract: "Contract") -> None | str | bool | float | date:
        if not hasattr(contract, "_annual_info_data"):
            contract._logger.warning(
                "You need to call get_annual_consumption method first"
            )
            return None
        if not contract._annual_info_data:
            contract._logger.info(
                "It seems Hydro-Québec didn't provided some data. "
                "Maybe you did a rate change recently. "
                "This message should disappear at the beginning of the next bill period."
            )
            return None
        return method(contract)

    return wrapper


def check_outages_data_present(method: Callable[P, T]) -> Callable[P, T]:
    """Check if contract's data are present."""

    @functools.wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        contract = cast("Contract", args[0])
        if hasattr(contract, "_outages_data"):
            return method(*args, **kwargs)

        contract._logger.warning("You need to call refresh_outages method first")
        return cast(T, None)

    return wrapper


class Contract(ABC):
    """Hydroquebec contract.

    Represents a contract (contrat)
    """

    _mve_activated: bool
    _rate_code: str
    _rate_option_code: str
    _meter_id: str
    _address: str
    _raw_info_data: ContractTyping
    _annual_info_data: ConsumpAnnualTyping
    _outages_data: OutageListTyping
    _all_period_data: list[PeriodDataTyping]

    def __init__(
        self,
        applicant_id: str,
        customer_id: str,
        *,
        account_id: str,
        contract_id: str,
        hydro_client: HydroClient,
        log_level: str | None = None,
    ):
        """Create a new Hydroquebec contract."""
        self._logger: logging.Logger = get_logger(
            f"c-{contract_id}",
            log_level=log_level,
            parent=f"w-{applicant_id}.c-{customer_id}.a-{account_id}",
        )
        self._no_partenaire_demandeur: str = applicant_id
        self._no_partenaire_titulaire: str = customer_id
        self._no_compte_contrat: str = account_id
        self._no_contrat: str = contract_id
        self._hydro_client: HydroClient = hydro_client
        self._address: str = ""
        self._outages: list[Outage] = []

    # Main attributes
    @property
    def applicant_id(self) -> str:
        """Get applicant id."""
        return self._no_partenaire_demandeur

    @property
    def customer_id(self) -> str:
        """Get customer id."""
        return self._no_partenaire_titulaire

    @property
    def account_id(self) -> str:
        """Get account id."""
        return self._no_compte_contrat

    @property
    def contract_id(self) -> str:
        """Get contract id."""
        return self._no_contrat

    @property
    def rate(self) -> str:
        """Get current period rate name."""
        if hasattr(self, "_rate_code"):
            return self._rate_code
        return "Unknown rate"

    @property
    def rate_option(self) -> str:
        """Get current period rate option name."""
        return self._rate_option_code

    @property
    @check_info_data_present
    def address(self) -> str:
        """Get contract address."""
        return self._raw_info_data["adresseConsommation"].strip()

    @property
    @check_info_data_present
    def meter_id(self) -> str:
        """Get meter id."""
        return self._raw_info_data["noCompteur"]

    @property
    @check_info_data_present
    def start_date(self) -> date:
        """Get contract start date."""
        start_date = date.fromisoformat(
            self._raw_info_data["dateDebutContrat"].split("T")[0]
        )
        return start_date

    @property
    @check_info_data_present
    def consumption_location_id(self) -> str:
        """Get consumption location id."""
        return self._raw_info_data["idLieuConsommation"]

    # Main methods
    async def get_info(self) -> ContractTyping:
        """Fetch info about this contract."""
        self._logger.debug("Getting contract info")
        self._raw_info_data = await self._hydro_client.get_contract_info(
            self.applicant_id, self.customer_id, self.account_id, self.contract_id
        )
        self._logger.debug("Got contract info")
        return self._raw_info_data

    async def get_periods_info(self) -> list[PeriodDataTyping]:
        """Fetch periods info."""
        self._logger.debug("Getting contract periods info")
        self._all_period_data = await self._hydro_client.get_periods_info(
            self.applicant_id, self.customer_id, self.contract_id
        )
        self._logger.debug("Got contract periods info")
        return self._all_period_data

    @property
    @check_period_data_present
    def latest_period_info(self) -> PeriodDataTyping:
        """Fetch latest period info."""
        return self._all_period_data[0]

    async def refresh_outages(self) -> None:
        """Fetch contract outages."""
        if self.consumption_location_id is not None:
            res = await self._hydro_client.get_outages(
                str(self.consumption_location_id)
            )
            if res is not None:
                self._outages_data = res
                self._outages = []
                for raw_outage in self._outages_data["interruptions"]:
                    self._outages.append(Outage(raw_outage, self._logger))
                self._outages.sort(key=lambda x: x.start_date)

    @property
    @check_outages_data_present
    def outages(self) -> list[Outage]:
        """Return the list of the contract outages."""
        return self._outages

    @property
    @check_outages_data_present
    def next_outage(self) -> Outage | None:
        """Get next or first contract outage."""
        if self._outages:
            return self.outages[0]
        return None

    # Consumption methods
    async def get_today_hourly_consumption(self) -> ConsumpHourlyTyping:
        """Fetch hourly consumption for today."""
        return await self._hydro_client.get_today_hourly_consumption(
            self.applicant_id, self.customer_id, self.contract_id
        )

    async def get_hourly_consumption(self, date_wanted: date) -> ConsumpHourlyTyping:
        """Fetch hourly consumption for a date."""
        return await self._hydro_client.get_hourly_consumption(
            self.applicant_id, self.customer_id, self.contract_id, date_wanted
        )

    async def get_daily_consumption(
        self, start_date: date, end_date: date
    ) -> ConsumpDailyTyping:
        """Fetch daily consumption."""
        return await self._hydro_client.get_daily_consumption(
            self.applicant_id,
            self.customer_id,
            contract_id=self.contract_id,
            start_date=start_date,
            end_date=end_date,
        )

    async def get_today_daily_consumption(self) -> ConsumpDailyTyping:
        """TODO ????.

        .. todo::
            document this method
        """
        today = datetime.today().astimezone(EST_TIMEZONE)
        yesterday = today - timedelta(days=1)
        return await self.get_daily_consumption(yesterday, today)

    async def get_monthly_consumption(self) -> ConsumpMonthlyTyping:
        """Fetch monthly consumption."""
        return await self._hydro_client.get_monthly_consumption(
            self.applicant_id, self.customer_id, self.contract_id
        )

    async def get_annual_consumption(self) -> ConsumpAnnualTyping:
        """Fetch annual consumption."""
        self._annual_info_data = await self._hydro_client.get_annual_consumption(
            self.applicant_id, self.customer_id, self.contract_id
        )
        return self._annual_info_data

    # CSV methods
    async def get_daily_energy(
        self,
        start_date: date,
        end_date: date,
        raw_output: bool = False,
    ) -> Iterator[list[str | int | float]] | StringIO:
        """Get daily energy and power data on a specific date range.

        date format: 2022-11-23
        """
        data_csv = await self._hydro_client.get_consumption_csv(
            self.applicant_id,
            self.customer_id,
            contract_id=self.contract_id,
            start_date=start_date,
            end_date=end_date,
            option="energie-jour",
            raw_output=raw_output,
        )
        return data_csv

    async def get_hourly_energy(
        self,
        start_date: date,
        end_date: date,
        raw_output: bool = False,
    ) -> Iterator[list[str | int | float]] | StringIO:
        """Get hourly energy on a specific date range.

        date format: 2022-11-23
        """
        data_csv = await self._hydro_client.get_consumption_csv(
            self.applicant_id,
            self.customer_id,
            contract_id=self.contract_id,
            start_date=start_date,
            end_date=end_date,
            option="energie-heure",
            raw_output=raw_output,
        )
        return data_csv

    async def get_consumption_overview_csv(
        self,
        raw_output: bool = False,
    ) -> Iterator[list[str | int | float]] | StringIO:
        """Get the consumption overview over the last 2 years."""
        data_csv = await self._hydro_client.get_consumption_overview_csv(
            self.applicant_id,
            self.customer_id,
            self.contract_id,
            raw_output,
        )
        return data_csv

    # Current period attributes
    # CP == Current period
    @property
    @check_period_data_present
    def cp_current_day(self) -> int:
        """Get number of days since the current period started."""
        return self._all_period_data[0]["nbJourLecturePeriode"]

    @property
    @check_period_data_present
    def cp_duration(self) -> int:
        """Get current period duration in days."""
        return self._all_period_data[0]["nbJourPrevuPeriode"]

    @property
    @check_period_data_present
    def cp_current_bill(self) -> float:
        """Get current bill since the current period started."""
        return self._all_period_data[0]["montantFacturePeriode"]

    @property
    @check_period_data_present
    def cp_projected_bill(self) -> float:
        """Projected bill of the current period."""
        return float(self._all_period_data[0].get("montantProjetePeriode", 0))

    @property
    @check_period_data_present
    def cp_daily_bill_mean(self) -> float:
        """Daily bill mean since the current period started."""
        return self._all_period_data[0]["moyenneDollarsJourPeriode"]

    @property
    @check_period_data_present
    def cp_daily_consumption_mean(self) -> float:
        """Daily consumption mean since the current period started."""
        return self._all_period_data[0]["moyenneKwhJourPeriode"]

    @property
    @check_period_data_present
    def cp_total_consumption(self) -> float:
        """Total consumption since the current period started."""
        return self._all_period_data[0]["consoTotalPeriode"]

    @property
    @check_period_data_present
    def cp_projected_total_consumption(self) -> float:
        """Projected consumption of the current period started."""
        return self._all_period_data[0]["consoTotalProjetePeriode"]

    @property
    @check_period_data_present
    def cp_average_temperature(self) -> float:
        """Average temperature since the current period started."""
        return self._all_period_data[0]["tempMoyennePeriode"]

    @property
    @check_period_data_present
    def cp_kwh_cost_mean(self) -> float | None:
        """Mean cost of a kWh since the current period started."""
        if self._all_period_data[0]["coutCentkWh"] is not None:
            return self._all_period_data[0]["coutCentkWh"] / 100
        return None

    @property
    @check_period_data_present
    def cp_epp_enabled(self) -> bool:
        """Is EPP enabled for the current period.

        See: https://www.hydroquebec.com/residential/customer-space/
             account-and-billing/equalized-payments-plan.html
        """
        return self._all_period_data[0]["indMVEPeriode"]

    # Repr
    def __repr__(self) -> str:
        """Represent object."""
        return (
            f"""<Contract - {self.rate}|{self.rate_option} - """
            f"""{self.applicant_id} - {self.customer_id} - """
            f"""{self.account_id} - {self.contract_id}>"""
        )


class ContractFallBack(Contract):
    """Hydroquebec fallback contract.

    Represents a contract (contrat) not supported by the library.
    It will just have a basic features of a contract and could crash anytime.
    """

    _rate_code = "FALLBACK"
    _rate_option_code = ""

    def __init__(
        self,
        applicant_id: str,
        customer_id: str,
        *,
        account_id: str,
        contract_id: str,
        hydro_client: HydroClient,
        log_level: str | None = None,
    ):
        """Create a new Hydroquebec contract."""
        Contract.__init__(
            self,
            applicant_id,
            customer_id,
            account_id=account_id,
            contract_id=contract_id,
            hydro_client=hydro_client,
            log_level=log_level,
        )
