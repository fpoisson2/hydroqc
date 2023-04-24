"""Hydroqc API Consts.

.. todo::

    avoid all the /portail/ URLs
"""
# Always get the time using HydroQuebec Local Time
REQUESTS_TIMEOUT = 30
REQUESTS_TTL = 1

HOST_LOGIN = "https://connexion.hydroquebec.com"
HOST_SESSION = "https://session.hydroquebec.com"
HOST_SERVICES = "https://cl-services.idp.hydroquebec.com"
HOST_SPRING = "https://cl-ec-lsw.solutions.hydroquebec.com"
HOST_RB_SOL = "https://rb.solutions.hydroquebec.com"
HOST_OUTAGES = "https://infopannes-services.solutions.hydroquebec.com"

# Outages
OUTAGES = f"{HOST_OUTAGES}/web/api/v1/lieux-conso/etats/"
# OAUTH PATHS
LOGIN_URL_1 = f"{HOST_LOGIN}/hqam/XUI/"  # not used
LOGIN_URL_2 = f"{HOST_LOGIN}/hqam/json/serverinfo/*"  # not used
AUTH_URL = f"{HOST_LOGIN}/hqam/json/realms/root/realms/clients/authenticate"
SECURITY_URL = f"{HOST_SESSION}/config/security.json"
TOKEN_URL = f"{HOST_LOGIN}/hqam/oauth2/access_token"
SESSION_REFRESH_URL = f"{HOST_SESSION}/oauth2/callback/silent-refresh"
AUTHORIZE_URL = f"{HOST_LOGIN}/hqam/oauth2/authorize"
LOGIN_URL_6 = f"{HOST_SERVICES}/cl/prive/api/v3_0/conversion/codeAcces"
CHECK_SESSION_URL = f"{HOST_LOGIN}/hqam/oauth2/connect/checkSession"
# Initialization uri
RELATION_URL = f"{HOST_SERVICES}/cl/prive/api/v1_0/relations"

# TODO avoid all the /portail/ URLs
PORTRAIT_URL = f"{HOST_SPRING}/portail/fr/group/clientele/portrait-de-consommation"

FLEXD_DATA_URL = f"{PORTRAIT_URL}/" "resourceObtenirDonneesMoisHiverFlex"
FLEXD_PEAK_URL = f"{HOST_RB_SOL}/portraitweb/api/v3_0/conso"
CONSO_CSV_URL = f"{PORTRAIT_URL}/" "resourceTelechargerDonneesConsommation"
CONSO_OVERVIEW_CSV_URL = (
    f"{HOST_SPRING}/portail/en/group/clientele/portrait-de-consommation/"
    "resourceTelechargerPeriodesFacturation"
)

# TODO avoid all the /portail/ URLs
SESSION_URL = f"{HOST_SPRING}/portail/prive/maj-session/"
# TODO avoid all the /portail/ URLs
CONTRACT_HTML_URL = f"{HOST_SPRING}/portail/fr/group/clientele/gerer-mon-compte"
#
INFOBASE_URL = f"{HOST_SERVICES}/cl/prive/api/v3_0/partenaires/infoBase"
CONTRACT_SUMMARY_URL = (
    f"{HOST_SERVICES}/cl/prive/api/v3_0/partenaires/"
    "calculerSommaireContractuel?indMAJNombres=true"
)
CONTRACT_LIST_URL = f"{HOST_SERVICES}/cl/prive/api/v3_0/partenaires/contrats"
# CONTRACT_URL_4 = (f"{HOST_SERVICES}/cl/prive/api/v3_0/partenaires/"
#                  "calculerSommaireContractuel")

CUSTOMER_INFO_URL = f"{HOST_SERVICES}/cl/prive/api/v3_0/partenaires/infoCompte"

# TODO avoid all the /portail/ URLs
PERIOD_DATA_URL = f"{PORTRAIT_URL}/" "resourceObtenirDonneesPeriodesConsommation"

# TODO avoid all the /portail/ URLs
ANNUAL_DATA_URL = f"{PORTRAIT_URL}/" "resourceObtenirDonneesConsommationAnnuelles"

# TODO avoid all the /portail/ URLs
MONTHLY_DATA_URL = f"{PORTRAIT_URL}/" "resourceObtenirDonneesConsommationMensuelles"

# TODO avoid all the /portail/ URLs
DAILY_CONSUMPTION_API_URL = (
    f"{PORTRAIT_URL}/" "resourceObtenirDonneesQuotidiennesConsommation"
)

# TODO avoid all the /portail/ URLs
HOURLY_CONSUMPTION_API_URL = (
    f"{PORTRAIT_URL}/" "resourceObtenirDonneesConsommationHoraires"
)
# TODO avoid all the /portail/ URLs
HOURLY_DATA_URL_2 = f"{PORTRAIT_URL}/" "resourceObtenirDonneesMeteoHoraires"  # not used

# CPC
GET_CPC_API_URL = (
    f"{HOST_SERVICES}/cl/prive/api/v3_0/tarificationDynamique/creditPointeCritique"
)

# IS PORTAL RUNNING
IS_HYDRO_PORTAL_UP_URL = f"{HOST_SESSION}/portail/fr/group/clientele/gerer-mon-compte"
