"""Select the latest Home Assistant release and a compatible runner Python."""

import json
import os
from urllib.request import urlopen

from packaging.specifiers import SpecifierSet
from packaging.version import Version


def load_json(url):
    """Fetch JSON metadata from a public endpoint."""
    with urlopen(url, timeout=30) as response:
        return json.load(response)


home_assistant = load_json("https://pypi.org/pypi/homeassistant/json")["info"]
home_assistant_version = home_assistant["version"]
if Version(home_assistant_version).is_prerelease:
    raise SystemExit("The latest Home Assistant release is not stable")

requires_python = SpecifierSet(home_assistant["requires_python"])
manifest = load_json(
    "https://raw.githubusercontent.com/actions/python-versions/main/versions-manifest.json"
)
available = [
    Version(entry["version"])
    for entry in manifest
    if entry["stable"]
    and Version(entry["version"]) in requires_python
    and any(
        file["platform"] == "linux"
        and file["arch"] == "x64"
        and file.get("platform_version") == "24.04"
        for file in entry["files"]
    )
]
if not available:
    raise SystemExit(f"No runner Python version satisfies {requires_python}")

oldest_minor = min((version.major, version.minor) for version in available)
python_version = str(
    max(version for version in available if version.release[:2] == oldest_minor)
)
print(f"Home Assistant {home_assistant_version} requires Python {requires_python}")
print(f"Selected Python {python_version}")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    print(f"home_assistant={home_assistant_version}", file=output)
    print(f"python={python_version}", file=output)
