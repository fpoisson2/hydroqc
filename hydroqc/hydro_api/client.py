"""HydroQc Client Module."""
import base64
import csv
import json
import logging
import os
import platform
import re
import ssl
import uuid
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from io import StringIO
from json import dumps as json_dumps
from typing import Any

import aiohttp
import yarl
from pkce import generate_pkce_pair

from hydroqc.error import HydroQcError, HydroQcHTTPError
from hydroqc.hydro_api.cache import CCached
from hydroqc.hydro_api.consts import (
    ANNUAL_DATA_URL,
    AUTH_CALLBACK_URL,
    AUTH_URL,
    AUTHORIZE_URL,
    AZB2C_CLIENT_ID_WEB,
    AZB2C_POLICY,
    AZB2C_SCOPE_WEB,
    AZB2C_TIMEOUT_SKEW_SECS,
    CONSO_CSV_URL,
    CONSO_OVERVIEW_CSV_URL,
    CONTRACT_LIST_URL,
    CONTRACT_SUMMARY_URL,
    CUSTOMER_INFO_URL,
    DAILY_CONSUMPTION_API_URL,
    FLEXD_DATA_URL,
    FLEXD_PEAK_URL,
    GET_CPC_API_URL,
    HOURLY_CONSUMPTION_API_URL,
    IS_HYDRO_PORTAL_UP_URL,
    MONTHLY_DATA_URL,
    OUTAGES,
    PERIOD_DATA_URL,
    PORTRAIT_URL,
    RELATION_URL,
    REQUESTS_TIMEOUT,
    SESSION_URL,
    TOKEN_URL,
)
from hydroqc.logger import get_logger
from hydroqc.types import (
    AccountContractSummaryTyping,
    AccountTyping,
    ConsumpAnnualTyping,
    ConsumpDailyTyping,
    ConsumpHourlyTyping,
    ConsumpMonthlyTyping,
    ContractTyping,
    CPCDataTyping,
    DPCDataTyping,
    DPCPeakListDataTyping,
    IDTokenTyping,
    InfoAccountTyping,
    ListAccountsContractsTyping,
    ListContractsTyping,
    OutageListTyping,
    PeriodDataTyping,
)
from hydroqc.utils import EST_TIMEZONE


class HydroClient:
    """HydroQc HTTP Client."""

    def __init__(
        self,
        username: str,
        password: str,
        timeout: int = REQUESTS_TIMEOUT,
        verify_ssl: bool = True,
        session: aiohttp.ClientSession | None = None,
        log_level: str | None = "INFO",
        diag_folder: str | None = None,
    ):
        """Initialize the client object."""
        self.username: str = username
        self.password: str = password
        self._timeout: int = timeout
        self._session: aiohttp.ClientSession | None = session
        self._cookie_jar: aiohttp.CookieJar = aiohttp.CookieJar()
        self._verify_ssl: bool = verify_ssl

        # OAuth handling variables
        self._id_token: str = ""
        self.access_token: str = ""
        self.access_token_expiry: datetime = datetime.now()
        self.refresh_token: str = ""
        self.refresh_token_expiry: datetime = datetime.now()
        self.web_session_expiry: datetime = datetime.now()

        self._selected_customer: str
        self._selected_contract: str
        self._diag_folder: str | None = diag_folder
        self._diag_id: int = 0
        self.guid: str = str(uuid.uuid1())
        self._logger: logging.Logger = get_logger("httpclient", log_level)
        self._logger.debug("HydroQc initialized")
        self.reset()

    def reset(self) -> None:
        """Reset collected data and temporary variable."""
        self._id_token = ""
        self.access_token = ""
        self.access_token_expiry = datetime.now()
        self.refresh_token = ""
        self.refresh_token_expiry = datetime.now()
        self.web_session_expiry = datetime.now()
        self._cookie_jar = aiohttp.CookieJar()
        self._selected_customer = ""
        self._selected_contract = ""

    @property
    def user_agent(self) -> str:
        """Get http client user_agent."""
        try:
            hydroqc_version = version("Hydro_Quebec_API_Wrapper")
        except PackageNotFoundError:
            # package is not installed
            self._logger.warning(
                "Python package `Hydro_Quebec_API_Wrapper` is not installed. "
                "Install it using pip"
            )
            hydroqc_version = "unkwown"
        os_name = platform.system()
        return f"Hydroqc/{hydroqc_version} (dev@hydroqc.ca; https://gitlab.com/hydroqc) {os_name}"

    async def http_request(
        self,
        url: str,
        method: str,
        params: dict[str, Any] | None = None,
        data: str | dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        verify_ssl: bool | None = None,
        status: int | None = 200,
        url_encoded: bool = False,
    ) -> aiohttp.ClientResponse:
        """Make an HTTP request."""
        if params is None:
            params = {}
        if data is None:
            data = {}
        if headers is None:
            headers = {}
        headers["User-Agent"] = self.user_agent
        if verify_ssl is None:
            verify_ssl = self._verify_ssl

        ssl_context: ssl.SSLContext | None = None
        if verify_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.set_ciphers("DEFAULT")  # Needed for python3.10

        # Query Diagnostic
        if self._diag_folder is not None:
            cleaned_url = url.replace("/", "_").replace(":", "").split("#", 1)[0]
            diag_file_path = os.path.join(
                self._diag_folder,
                f"hq_{self._diag_id:02}_q_{method}_{cleaned_url}.json"[:128],
            )
            with open(diag_file_path, "w", encoding="utf-8") as fhj:
                json.dump(
                    {
                        "url": url,
                        "params": params,
                        "data": data,
                        # TODO Remove tokens
                        "headers": headers,
                    },
                    fhj,
                    indent=2,
                )

        self._logger.debug("HTTP query %s to %s", url, method)

        url_url = yarl.URL(url, encoded=url_encoded)
        raw_res: aiohttp.ClientResponse = await getattr(self._session, method)(
            url_url,
            params=params,
            data=data,
            allow_redirects=False,
            ssl=ssl_context,
            headers=headers,
        )

        # Result Diagnostic
        if self._diag_folder is not None:
            cleaned_url = url.replace("/", "_").replace(":", "").split("#", 1)[0]
            diag_file_path = os.path.join(
                self._diag_folder,
                f"hq_{self._diag_id:02}_r_{method}_{cleaned_url}.json"[:128],
            )
            diag_result = await raw_res.text()
            try:
                diag_result = json.dumps(json.loads(diag_result), indent=2)

            except json.JSONDecodeError:
                pass

            with open(diag_file_path, "w", encoding="utf-8") as fhj:
                fhj.write(diag_result)
            # Increment diag_id
            self._diag_id += 1

        if raw_res.status != status:
            self._logger.exception("Exception in http_request")
            data = await raw_res.text()
            self._logger.debug(data)
            raise HydroQcHTTPError(
                f"Error Fetching {url} - {raw_res.status}", raw_res.status
            )

        return raw_res

    def _load_json(self, data: str | bytes) -> Any:
        """Safely read json, raise a HydroQcHTTPError when parsing fails."""
        try:
            return json.loads(data)
        except json.decoder.JSONDecodeError as exp:
            self._logger.debug("JSON received : ", data)
            raise HydroQcHTTPError("Bad JSON format") from exp

    def get_token_data(self) -> IDTokenTyping:
        """Decode id token data."""
        raw_token_data = self._id_token.split(".")[1]
        # In some cases padding get lost, adding it to avoid issues with base64 decode
        raw_token_data += "=" * ((4 - len(raw_token_data) % 4) % 4)
        token_data: IDTokenTyping = self._load_json(base64.b64decode(raw_token_data))
        return token_data

    def _get_httpsession(self) -> None:
        """Set http session."""
        if self._session is None:
            self._logger.debug("Creating new http session")
            self._session = aiohttp.ClientSession(
                requote_redirect_url=False, cookie_jar=self._cookie_jar
            )

    async def _get_customer_http_headers(
        self, applicant_id: str, customer_id: str, force_refresh: bool = False
    ) -> dict[str, str]:
        """Prepare http headers for customer url queries."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + await self._get_access_token(force_refresh),
            "NO_PARTENAIRE_DEMANDEUR": applicant_id,
            "NO_PARTENAIRE_TITULAIRE": customer_id,
            "DATE_DERNIERE_VISITE": datetime.now().strftime(
                "%Y-%m-%dT%H:%M:%S.000+0000"
            ),
            "GUID_SESSION": self.guid,
        }
        return headers

    async def close_session(self) -> None:
        """Close current session."""
        if self._session is not None:
            self._logger.debug("Closing http session")
            await self._session.close()
            self._session = None

    async def check_portal_status(self) -> bool:
        """Check if Hydro Quebec portal is UP."""
        # Get http session
        self._get_httpsession()
        self._logger.info("Checking if the Hydro Quebec portal is UP")
        api_call_response = await self.http_request(
            IS_HYDRO_PORTAL_UP_URL,
            "get",
        )
        if api_call_response.status != 200:
            # TODO Add reason ?
            return False
        return True

    async def login(self) -> bool:
        """Log in HydroQuebec website.

        Hydroquebec is using B2C solution for authentication.
        """
        self._logger.info("Login using %s", self.username)

        # Reset cache
        self.reset()

        # Get code verifier and challenge
        code_verifier, code_challenge = generate_pkce_pair()

        # Get http session
        self._get_httpsession()

        url = f"{AUTHORIZE_URL}"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        params = {
            "redirect_uri": AUTH_CALLBACK_URL,
            "client_id": AZB2C_CLIENT_ID_WEB,
            "response_type": "code",
            "scope": AZB2C_SCOPE_WEB,
            "prompt": "login",
            "ui_locales": "fr",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "mobile": "false",
        }

        res = await self.http_request(url, "get", headers=headers, params=params)

        html_data = await res.text()

        # Extract the CSRF token
        if csrf_match := re.search(r'csrf":"(.+?)"', html_data):
            csrf_token = csrf_match.group(1)
        else:
            self._logger.error("Login error finding csrf token")
            return False

        # Extract the transId
        if transid_match := re.search(r'transId":"(.+?)"', html_data):
            transid = transid_match.group(1)
        else:
            self._logger.error("Login error finding trans Id")
            return False

        # POST https://connexion.solutions.hydroquebec.com/32bf9b91-0a36-4385-b231-d9a8fa3b05ab/
        # B2C_1A_PRD_signup_signin/SelfAsserted?tx=(transId value previously extracted)
        # &p=B2C_1A_PRD_signup_signin
        # with the following URLEncoded Form data

        # request_type: RESPONSE
        # signInName:   loginemail
        # password:     password
        #
        # The following http headers
        # content-type:      application/x-www-form-urlencoded; charset=UTF-8
        # accept:            application/json, text/javascript, */*; q=0.01
        #
        # Set the x-csrf-token header with the value previously extracted
        #
        # and the cookies captured in the last request
        url = AUTH_URL + "?tx=" + transid + "&p=" + AZB2C_POLICY
        headers = {
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "accept": "application/json, text/javascript, */*; q=0.01",
            "x-csrf-token": csrf_token,
        }

        data = {
            "request_type": "RESPONSE",
            "signInName": self.username,
            "password": self.password,
        }
        res = await self.http_request(url, "post", headers=headers, data=data)
        res_text = await res.text()
        res_json = json.loads(res_text)

        if res_json.get("status") != "200":
            self._logger.error("Login error - %s", res_json.get("message", "unknown"))
            return False

        # Call GET https://connexion.solutions.hydroquebec.com/32bf9b91-0a36-4385-b231-d9a8fa3b05ab/
        # B2C_1A_PRD_signup_signin/api/CombinedSigninAndSignup/confirmed?rememberMe=false
        # &csrf_token=(previously extracted csrf token)&tx=(previously extracted transId value)
        # &p=B2C_1A_PRD_signup_signin
        # with the session cookies
        # and the following http headers
        # accept:           text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
        #
        # and extract the code attribute from the location header of the response which
        #  has the following format:
        # location: msauth.com.hydroquebec.infos-pannes://
        # auth/?state=%257B%2522redirectUrl%2522%3a%2522CONSO%2522%257D&code=(code value)

        # Set the HTTP request parameters

        url = (
            "https://connexion.solutions.hydroquebec.com/32bf9b91-0a36-4385-b231-d9a8fa3b05ab"
            + "/B2C_1A_PRD_signup_signin/api/CombinedSigninAndSignup/"
            + "confirmed?rememberMe=false&csrf_token="
            + csrf_token
            + "&tx="
            + transid
            + "&p="
            + AZB2C_POLICY
        )
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        # Execute the http request
        res = await self.http_request(url, "get", headers=headers, status=302)

        # Extract the code attribute from the location header
        if code_match := re.search(r"code=(.+?)$", res.headers["Location"]):
            code = code_match.group(1)
        else:
            self._logger.error("Login error finding code attribute in location header")
            return False

        # POST https://connexion.solutions.hydroquebec.com/32bf9b91-0a36-4385-b231-d9a8fa3b05ab/
        # b2c_1a_prd_signup_signin/oauth2/v2.0/token HTTP/2.0
        # with the following URLEncoded Form data
        # grant_type:    authorization_code
        # client_id:     09b0ae72-6db8-4ecc-a1be-041b67afc1cd
        # redirect_uri:  msauth.com.hydroquebec.infos-pannes://auth
        # code:        (previously extracted code)
        # code_verifier: (previously generated code_verifier)

        # and the following http headers
        # content-type: application/x-www-form-urlencoded
        # accept:      */*
        #

        # Set the HTTP request parameters
        url = (
            "https://connexion.solutions.hydroquebec.com/32bf9b91-0a36-4385-b231-d9a8fa3b05ab/"
            + "b2c_1a_prd_signup_signin/oauth2/v2.0/token"
        )
        headers = {"content-type": "application/x-www-form-urlencoded", "accept": "*/*"}

        data = {
            "grant_type": "authorization_code",
            "client_id": AZB2C_CLIENT_ID_WEB,
            "redirect_uri": AUTH_CALLBACK_URL,
            "code": code,
            "code_verifier": code_verifier,
        }

        # Execute the http request
        res = await self.http_request(url, "post", headers=headers, data=data)
        res_json = await res.json()

        self._id_token = res_json["id_token"]
        self.access_token = res_json["access_token"]
        self.access_token_expiry = datetime.now() + timedelta(
            seconds=int(res_json["expires_in"]) - AZB2C_TIMEOUT_SKEW_SECS
        )
        self.refresh_token = res_json["refresh_token"]
        self.refresh_token_expiry = datetime.now() + timedelta(
            seconds=int(res_json["refresh_token_expires_in"]) - AZB2C_TIMEOUT_SKEW_SECS
        )

        self._logger.info("Login completed using %s", self.username)

        return True

    async def _refresh_token(self) -> bool:
        """Refresh current session."""
        self._logger.debug("Refreshing access token")

        url = TOKEN_URL
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/plain, */*",
        }
        data = {
            "grant_type": "refresh_token",
            "scope": AZB2C_SCOPE_WEB,
            "client_id": AZB2C_CLIENT_ID_WEB,
            "refresh_token": self.refresh_token,
        }

        res = await self.http_request(url, "post", headers=headers, data=data)
        res_json = await res.json()

        self._id_token = res_json["id_token"]
        self.access_token = res_json["access_token"]
        self.access_token_expiry = datetime.now() + timedelta(
            seconds=int(res_json["expires_in"]) - AZB2C_TIMEOUT_SKEW_SECS
        )
        self.refresh_token = res_json["refresh_token"]
        self.refresh_token_expiry = datetime.now() + timedelta(
            seconds=int(res_json["refresh_token_expires_in"]) - AZB2C_TIMEOUT_SKEW_SECS
        )

        return True

    def is_session_expired(self) -> bool:
        """Check if the session is expired."""
        return self.refresh_token_expiry < datetime.now()

    async def _get_access_token(self, force_refresh: bool = True) -> str:
        """Get an access token."""
        if self.is_session_expired():
            await self.close_session()
            await self.login()
        elif force_refresh or self.access_token_expiry < datetime.now():
            await self._refresh_token()

        return self.access_token

    @property
    def selected_customer(self) -> str:
        """Return the current selected customer."""
        return self._selected_customer

    @property
    def selected_contract(self) -> str:
        """Return the current selected contract."""
        return self._selected_contract

    async def _create_web_session(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> None:
        """Create a web session from a OAuth access_token."""
        self._logger.debug("Creating new web session %s", contract_id)

        # Clearing all cookies. New SESSION must be created.
        self._cookie_jar.clear()

        # Forcing a refresh of the access token.
        # The new session that is created with SESSION_URL (/portal resources)
        # seemed to break (calls returning HTTP 400) in alignment with
        # the access_token expiry. With a new access_token, we can assume the web
        # session invalid at the same time as the access token that was used to create it.
        headers = await self._get_customer_http_headers(
            applicant_id, customer_id, force_refresh=True
        )

        params = {"mode": "web"}
        await self.http_request(SESSION_URL, "get", params=params, headers=headers)
        self.web_session_expiry = self.access_token_expiry

    async def _select_contract(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> None:
        """Create a web session from a OAuth access_token and select a customer on the Home page.

        Equivalent to click on the customer box on the Home page.
        """
        if self.web_session_expiry > datetime.now():
            self._logger.debug("Not refreshing web session")
            return

        await self._create_web_session(applicant_id, customer_id, contract_id)

        self._logger.info("Selecting contract %s", contract_id)

        params = {"noContrat": contract_id}
        await self.http_request(PORTRAIT_URL, "get", params=params)

        self._selected_contract = contract_id
        self._selected_customer = customer_id
        self._logger.info("Contract %s selected", contract_id)

    @CCached(ttl=21600)
    async def get_user_info(self) -> list[AccountTyping]:
        """Fetch user ids and customer ids.

        .. todo::
            Handle json load error
        """
        self._logger.info("Fetching webuser info")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + await self._get_access_token(),
        }
        res = await self.http_request(RELATION_URL, "get", headers=headers)
        # TODO http errors
        data: list[AccountTyping] = await res.json()
        return data

    @CCached(ttl=21600)
    async def get_customer_info(
        self, applicant_id: str, customer_id: str
    ) -> InfoAccountTyping:
        """Fetch customer data."""
        self._logger.info("Fetching customer info: c-%s", customer_id)
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        params = {"withCredentials": "true"}
        api_call_response = await self.http_request(
            CUSTOMER_INFO_URL,
            "get",
            headers=headers,
            params=params,
        )
        data: InfoAccountTyping = await api_call_response.json()
        return data

    @CCached(ttl=21600)
    async def get_periods_info(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> list[PeriodDataTyping]:
        """Fetch all periods info."""
        await self._select_contract(applicant_id, customer_id, contract_id)
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        res = await self.http_request(PERIOD_DATA_URL, "get", headers=headers)
        data = json.loads(await res.text())

        periods: list[PeriodDataTyping] = [
            p for p in data["results"] if p["numeroContrat"] == contract_id
        ]
        if not periods:
            raise HydroQcError(f"No period found for contract {contract_id}")
        return periods

    @CCached(ttl=21600)
    async def get_account_info(
        self, applicant_id: str, customer_id: str, account_id: str
    ) -> ListAccountsContractsTyping:
        """Fetch account data."""
        self._logger.info("Fetching account info: c-%s - a-%s", customer_id, account_id)
        data = await self.get_customer_info(applicant_id, customer_id)
        accounts = {
            a["noCompteContrat"]: a
            for a in data["infoCockpitPourPartenaireModel"]["listeComptesContrats"]
        }
        if account_id not in accounts:
            raise HydroQcError("Account not found")
        return accounts[account_id]

    @CCached(ttl=21600)
    async def list_account_contract(
        self, applicant_id: str, customer_id: str
    ) -> AccountContractSummaryTyping:
        """Get all  account_contract linked to a customer."""
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        res = await self.http_request(CONTRACT_SUMMARY_URL, "get", headers=headers)
        data: AccountContractSummaryTyping = await res.json()
        return data

    @CCached(ttl=21600)
    async def get_contract_info(
        self, applicant_id: str, customer_id: str, account_id: str, contract_id: str
    ) -> ContractTyping:
        """Fetch contract data."""
        self._logger.info(
            "Fetching contract info: c-%s - a-%s - c-%s",
            applicant_id,
            customer_id,
            contract_id,
        )
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        post_data = {
            "listeServices": ["PC"],
            "comptesContrats": [
                {
                    "listeNoContrat": [contract_id],
                    "noCompteContrat": account_id,
                    "titulaire": customer_id,
                }
            ],
        }
        post_data_str = json_dumps(post_data)
        res = await self.http_request(
            CONTRACT_LIST_URL, "post", headers=headers, data=post_data_str
        )
        data: ListContractsTyping = await res.json()
        # We ask only one contract, so we should have only one
        if not data["listeContrats"]:
            raise HydroQcError("Contract not found")
        return data["listeContrats"][0]

    @CCached(ttl=3600)
    async def get_cpc_credit(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> CPCDataTyping:
        """Return information about CPC option (winter credit).

        :return: raw JSON from hydro QC API
        """
        self._logger.info("Fetching cpc: c-%s c-%s", customer_id, contract_id)
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        params = {"noContrat": contract_id}
        api_call_response = await self.http_request(
            GET_CPC_API_URL,
            "get",
            headers=headers,
            params=params,
        )
        data: CPCDataTyping = await api_call_response.json()
        return data

    @CCached(ttl=900)
    async def get_outages(
        self, consumption_location_id: str
    ) -> OutageListTyping | None:
        """Return outages for a given consumption location id."""
        response = await self.http_request(OUTAGES + consumption_location_id, "get")
        res: list[OutageListTyping] = await response.json()
        return res[0] if res else None

    async def get_today_hourly_consumption(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> ConsumpHourlyTyping:
        """Return latest consumption info (about 2h delay it seems).

        :return: raw JSON from hydro QC API for current day (not officially supported, data delayed)
        """
        today = datetime.today().astimezone(EST_TIMEZONE).date()
        day_m2 = today - timedelta(days=2)
        day_m1 = today - timedelta(days=1)
        # We need to call a valid date first as theoretically today is invalid
        # and the api will not respond if called directly
        # We also get 2 days ago to not crash right after midnight
        await self.get_hourly_consumption(
            applicant_id, customer_id, contract_id, day_m2
        )
        await self.get_hourly_consumption(
            applicant_id, customer_id, contract_id, day_m1
        )
        res: ConsumpHourlyTyping = await self.get_hourly_consumption(
            applicant_id, customer_id, contract_id, today
        )
        return res

    @CCached(ttl=3600)
    async def get_hourly_consumption(
        self, applicant_id: str, customer_id: str, contract_id: str, date_wanted: date
    ) -> ConsumpHourlyTyping:
        """Return hourly consumption for a specific day.

        .. todo::
            Use decorator for self._select_contract

        :param: date: YYYY-MM-DD string to pass to API

        :return: raw JSON from hydro QC API
        """
        self._logger.info(
            "Fetching hourly consumption: c-%s c-%s", customer_id, contract_id
        )
        # TODO use decorator
        await self._select_contract(applicant_id, customer_id, contract_id)
        params = {"date": date_wanted.isoformat()}
        api_call_response = await self.http_request(
            HOURLY_CONSUMPTION_API_URL, "get", params=params
        )
        # We can not use res.json() because the response header are not application/json
        data: ConsumpHourlyTyping = self._load_json(await api_call_response.text())
        return data

    @CCached(ttl=43200)
    async def get_daily_consumption(
        self,
        applicant_id: str,
        customer_id: str,
        contract_id: str,
        start_date: date,
        end_date: date,
    ) -> ConsumpDailyTyping:
        """Return daily consumption for a specific day.

        .. todo::
            Use decorator for self._select_contract

        :param: start_date: date to pass to API
        :param: end_date: date to pass to API

        :return: raw JSON from hydro QC API
        """
        self._logger.info(
            "Fetching daily consumption: c-%s c-%s", customer_id, contract_id
        )
        # TODO use decorator
        await self._select_contract(applicant_id, customer_id, contract_id)
        params = {"dateDebut": start_date.isoformat(), "dateFin": end_date.isoformat()}
        api_call_response = await self.http_request(
            DAILY_CONSUMPTION_API_URL,
            "get",
            params=params,
        )
        # We can not use res.json() because the response header are not application/json
        data: ConsumpDailyTyping = self._load_json(await api_call_response.text())
        return data

    @CCached(ttl=21600)
    async def get_monthly_consumption(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> ConsumpMonthlyTyping:
        """Fetch data of the current year.

        .. todo::
            Use decorator for self._select_contract

        API URL: https://cl-ec-spring.hydroquebec.com/portail/fr/group/clientele/
        portrait-de-consommation/resourceObtenirDonneesConsommationMensuelles
        """
        self._logger.info(
            "Fetching monthly consumption: c-%s c-%s", customer_id, contract_id
        )
        # TODO use decorator
        await self._select_contract(applicant_id, customer_id, contract_id)
        headers = {"Content-Type": "application/json"}
        api_call_response = await self.http_request(
            MONTHLY_DATA_URL, "get", headers=headers
        )
        # We can not use res.json() because the response header are not application/json
        data: ConsumpMonthlyTyping = self._load_json(await api_call_response.text())
        return data

    @CCached(ttl=21600)
    async def get_annual_consumption(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> ConsumpAnnualTyping:
        """Fetch data of the current year.

        API URL: https://cl-ec-spring.hydroquebec.com/portail/fr/group/clientele/
        portrait-de-consommation/resourceObtenirDonneesConsommationAnnuelles
        """
        self._logger.info(
            "Fetching annual consumption: c-%s c-%s", customer_id, contract_id
        )
        await self._select_contract(applicant_id, customer_id, contract_id)
        headers = {"Content-Type": "application/json"}
        api_call_response = await self.http_request(
            ANNUAL_DATA_URL, "get", headers=headers
        )
        # We can not use res.json() because the response header are not application/json
        data: ConsumpAnnualTyping = self._load_json(await api_call_response.text())
        return data

    @CCached(ttl=21600)
    async def get_dpc_data(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> DPCDataTyping:
        """Fetch FlexD data of the current year.

        API URL: https://cl-ec-spring.hydroquebec.com/portail/fr/group/clientele/
        portrait-de-consommation/resourceObtenirDonneesMoisHiverFlex

        """
        await self._select_contract(applicant_id, customer_id, contract_id)
        api_call_response = await self.http_request(FLEXD_DATA_URL, "get")
        # We can not use res.json() because the response header are not application/json
        data: DPCDataTyping = self._load_json(await api_call_response.text())
        return data

    @CCached(ttl=3600)
    async def get_dpc_peak_data(
        self, applicant_id: str, customer_id: str, contract_id: str
    ) -> DPCPeakListDataTyping:
        """Fetch FlexD data of the current year.

        API URL: https://cl-ec-spring.hydroquebec.com/portail/fr/group/clientele/
        portrait-de-consommation/resourceObtenirDonneesMoisHiverFlex

        """
        await self._select_contract(applicant_id, customer_id, contract_id)
        headers = await self._get_customer_http_headers(applicant_id, customer_id)
        params = {"noContrat": contract_id}
        api_call_response = await self.http_request(
            FLEXD_PEAK_URL, "get", params=params, headers=headers
        )
        # We can not use res.json() because the response header are not application/json
        data: DPCPeakListDataTyping = self._load_json(await api_call_response.text())
        return data

    async def get_consumption_csv(
        self,
        applicant_id: str,
        customer_id: str,
        contract_id: str,
        start_date: date,
        end_date: date,
        option: str,
        raw_output: bool = False,
    ) -> Iterator[list[str | int | float]] | StringIO:
        """Download one of the history CSV on the portrait-de-consommation page.

        `option` should be one of 'puissance-jour', 'energie-heure',
                                  'puissance-min', 'energie-jour',
        """
        await self._select_contract(applicant_id, customer_id, contract_id)
        data = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "option": option,
        }
        res = await self.http_request(
            CONSO_CSV_URL,
            "post",
            data=data,
        )
        # TODO: improve this, with something like asyncsv
        # instead of loading all the csv in memory
        content = StringIO(await res.text())
        if raw_output:
            return content
        data_csv: Iterator[Any] = csv.reader(content, delimiter=";")
        return data_csv

    async def get_consumption_overview_csv(
        self,
        applicant_id: str,
        customer_id: str,
        contract_id: str,
        raw_output: bool = False,
    ) -> Iterator[list[str | int | float]] | StringIO:
        """Download the overview by consumption period CSV on the portrait-de-consommation page."""
        await self._select_contract(applicant_id, customer_id, contract_id)
        res = await self.http_request(CONSO_OVERVIEW_CSV_URL, "get")
        # TODO: improve this, with something like asyncsv
        # instead of loading all the csv in memory
        content = StringIO(await res.text())
        if raw_output:
            return content
        data_csv: Iterator[Any] = csv.reader(content, delimiter=";")
        return data_csv
