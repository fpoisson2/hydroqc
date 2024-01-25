"""Hydroquebec contract module."""
from collections.abc import Callable
from datetime import date

from hydroqc.contract.common import check_period_data_present
from hydroqc.contract.contract_residential import ContractResidential
from hydroqc.hydro_api.client import HydroClient
from hydroqc.peak.dpc.handler import DPCPeakHandler
from hydroqc.types import (
    ConsumpAnnualTyping,
    ContractTyping,
    CPCDataTyping,
    DPCDataTyping,
    OutageListTyping,
)


def check_dpc_data_present(
    method: Callable[..., None | str | bool | float | date]
) -> Callable[..., None | str | bool | float | date]:
    """Check if contractDPC's data are present."""

    def wrapper(contract: "ContractDPC") -> None | str | bool | float | date:
        if not hasattr(contract, "_dpc_data"):
            contract._logger.warning("You need to call get_dpc_data method first")
            return None

        if not contract._dpc_data:
            contract._logger.info(
                "It seems Hydro-Québec didn't provided some data. "
                "Maybe you did a rate change recently. "
                "This message should disappear at the beginning of the next bill period."
            )
        return method(contract)

    return wrapper


class ContractDPC(ContractResidential):
    """Hydroquebec contract.

    Represents a FlexD contract (contrat)
    """

    _rate_code = "DPC"
    _rate_option_code = ""
    _dpc_data: DPCDataTyping

    def __init__(
        self,
        applicant_id: str,
        customer_id: str,
        account_id: str,
        contract_id: str,
        hydro_client: HydroClient,
        log_level: str | None = None,
    ):
        """Create a new Hydroquebec contract."""
        ContractResidential.__init__(
            self,
            applicant_id,
            customer_id,
            account_id,
            contract_id,
            hydro_client,
            log_level,
        )
        peaks_logger = self._logger.getChild("peaks")
        self._peakh: DPCPeakHandler = DPCPeakHandler(
            self.applicant_id,
            self.customer_id,
            self.contract_id,
            hydro_client,
            peaks_logger,
        )

    @property
    def peak_handler(self) -> DPCPeakHandler:
        """Get peak handler object."""
        return self._peakh

    def set_preheat_duration(self, duration: int) -> None:
        """Set preheat duration in minutes."""
        self._peakh.set_preheat_duration(duration)

    async def get_dpc_data(self) -> DPCDataTyping:
        """Fetch FlexD data."""
        self._dpc_data = await self._hydro_client.get_dpc_data(
            self.applicant_id, self.customer_id, self.contract_id
        )
        return self._dpc_data

    @property
    @check_period_data_present
    def cp_lower_price_consumption(self) -> float:
        """Total lower priced consumption since the current period started."""
        return float(
            self._all_period_data[0]["consoTotalPeriode"]
            - self._all_period_data[0]["nbKwhConsoHautTarifFlexPeriode"]
        )

    @property
    @check_period_data_present
    def cp_higher_price_consumption_cost(self) -> float:
        """Total cost of critical peak consumption since the current period started."""
        return self._all_period_data[0]["montantVentePointeCritique"]

    @property
    @check_period_data_present
    def cp_higher_price_consumption(self) -> float:
        """Total higher priced consumption since the current period started."""
        return float(self._all_period_data[0]["nbKwhConsoHautTarifFlexPeriode"])

    @property
    @check_dpc_data_present
    def last_update_date(self) -> date:
        """DPC data last update."""
        return date.fromisoformat(self._dpc_data["results"][0]["dateDernMaj"])

    @property
    @check_dpc_data_present
    def critical_called_hours(self) -> int:
        """Get number of critical hours."""
        return int(self._dpc_data["results"][0]["hrsCritiquesAppelees"])

    @property
    @check_dpc_data_present
    def max_critical_called_hours(self) -> int:
        """Get max number of critical hours."""
        return int(self._dpc_data["results"][0]["hrsCritiquesAppeleesMax"])

    @property
    @check_dpc_data_present
    def amount_saved_vs_base_rate(self) -> float:
        """Amount saved or not versus the base rate."""
        return self._dpc_data["results"][0]["montantEconPerteVSTarifBase"]

    @property
    @check_dpc_data_present
    def winter_total_days(self) -> int:
        """Get number of winter days."""
        return self._dpc_data["results"][0]["nbJoursTotauxHiver"]

    @property
    @check_dpc_data_present
    def winter_total_days_last_update(self) -> int:
        """Get number of days since winter starts."""
        return self._dpc_data["results"][0]["nbJoursDernMaj"]

    @property
    @check_dpc_data_present
    def winter_state(self) -> str:
        """Get winter state.

        C: started
        ?: ???????
        """
        return self._dpc_data["results"][0]["etatHiver"]

    @property
    def raw_data(
        self,
    ) -> dict[
        str,
        ContractTyping
        | ConsumpAnnualTyping
        | OutageListTyping
        | CPCDataTyping
        | DPCDataTyping,
    ]:
        """Get a bunch of un processed data."""
        raw_data = super().raw_data
        if hasattr(self, "_dpc_data"):
            raw_data["dpc_data"] = self._dpc_data
        return raw_data
