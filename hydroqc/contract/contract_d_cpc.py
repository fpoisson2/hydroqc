"""Hydroquebec contract module."""
from hydroqc.contract.contract_d import ContractD
from hydroqc.hydro_api.client import HydroClient
from hydroqc.peak.cpc.handler import CPCPeakHandler
from hydroqc.types import (
    ConsumpAnnualTyping,
    ContractTyping,
    CPCDataTyping,
    DPCDataTyping,
    OutageListTyping,
)


class ContractDCPC(ContractD):
    """Hydroquebec contract.

    Represents a contract (contrat)
    """

    _rate_option_code = "CPC"

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
        ContractD.__init__(
            self,
            applicant_id,
            customer_id,
            account_id,
            contract_id,
            hydro_client,
            log_level,
        )
        wch_logger = self._logger.getChild("wch")
        self._wch: CPCPeakHandler = CPCPeakHandler(
            self.applicant_id,
            self.customer_id,
            self.contract_id,
            hydro_client,
            wch_logger,
        )

    @property
    def peak_handler(self) -> CPCPeakHandler:
        """Get peak helper object."""
        return self._wch

    def set_preheat_duration(self, duration: int) -> None:
        """Set preheat duration in minutes."""
        self._wch.set_preheat_duration(duration)

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
        raw_data["cpc_data"] = self._wch.raw_data
        return raw_data
