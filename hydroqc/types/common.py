"""Common types."""

# pylint: disable=invalid-name
from enum import Enum
from typing import Literal, TypedDict


class IDTokenTyping(TypedDict, total=True):
    """ID token output format."""

    at_hash: str
    sub: str
    displayName: str
    auditTrackingId: str
    roles: list[str]
    iss: str
    tokenName: str
    given_name: str
    locale: str
    nonce: str
    aud: str
    acr: str
    # org.forgerock.openidconnect.ops: str
    s_hash: str
    azp: str
    auth_time: int
    name: str
    realm: str
    exp: int
    tokenType: str
    family_name: str
    iat: int
    email: str


class Rates(Enum):
    """Contract Rates."""

    D = "D"
    DT = "DT"
    DPC = "DPC"
    M = "M"


class RateOptions(Enum):
    """Contract Rate Options."""

    CPC = "CPC"
    GDP = "GDP"


OpenDataPeakEventOffer = Literal[
    "OEA-M",
    "GDP-Affaires",
    "TPC-LC2",
    "CPC-D",
    "CPC-G",
    "TPC-DPC",
    "TPC-GPC",
    "TPC-M",
    "TPC-LD2",
    "OEA-L",
]


class OpenDataPeakEvent(TypedDict):
    """Peak event on open data source."""

    offre: OpenDataPeakEventOffer
    dateDebut: str
    dateFin: str
    plageHoraire: Literal["AM", "PM"]
    duree: str
    secteurClient: Literal["Affaires", "Residentielle"]


class OpenDataPeakEvents(TypedDict):
    """Peak event list on open data source."""

    evenements: list[OpenDataPeakEvent]
