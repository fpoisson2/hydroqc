"""Schema extraction and anonymization tool for API monitoring."""

import hashlib
import json
import os
import re
from datetime import datetime
from typing import Any


def anonymize_value(
    value: Any, key: str = ""
) -> Any:  # pylint: disable=too-many-return-statements
    """Anonymize sensitive data while preserving type and structure.

    Args:
        value: The value to anonymize
        key: The dictionary key (used for context-aware anonymization)

    Returns:
        Anonymized value preserving type
    """
    # Null/None values preserved
    if value is None:
        return None

    # Boolean values preserved
    if isinstance(value, bool):
        return value

    # Numeric values: preserve type, anonymize value
    if isinstance(value, (int, float)):
        # Preserve small integers that might be flags/codes (0-100)
        if isinstance(value, int) and 0 <= value <= 100:
            return value
        # Hash numeric values consistently
        hashed = hashlib.sha256(str(value).encode()).hexdigest()
        if isinstance(value, float):
            return float(int(hashed[:12], 16) % 1000000) / 100
        return int(hashed[:12], 16) % 1000000

    # String values: context-aware anonymization
    if isinstance(value, str):
        lower_key = key.lower()

        # Preserve empty strings
        if not value:
            return value

        # Date/time strings - preserve format, use fake date
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return "2024-01-15" + value[10:]  # Preserve time portion

        # Email addresses
        if "@" in value and re.match(r"^[^@]+@[^@]+\.[^@]+$", value):
            return "user@example.com"

        # IDs, numbers, account-related
        if any(
            x in lower_key
            for x in (
                "id",
                "no",
                "numero",
                "compte",
                "contrat",
                "partenaire",
                "compteur",
            )
        ):
            # Preserve length and numeric format
            if value.isdigit():
                return "1" * len(value)
            # Alphanumeric IDs
            hashed = hashlib.sha256(value.encode()).hexdigest()
            return (
                hashed[: len(value)].upper()
                if value.isupper()
                else hashed[: len(value)]
            )

        # Addresses
        if "adresse" in lower_key or "address" in lower_key:
            return "123 RUE EXAMPLE"

        # Names
        if "nom" in lower_key or "name" in lower_key or "prenom" in lower_key:
            return "ANONYMIZED"

        # Phone numbers
        if re.match(r"^\+?\d{10,}$", value.replace("-", "").replace(" ", "")):
            return "5555551234"

        # Postal codes (Canadian format)
        if re.match(r"^[A-Z]\d[A-Z]\s?\d[A-Z]\d$", value):
            return "H1H 1H1"

        # Default: preserve format markers but hash content
        if len(value) < 3:
            return value  # Preserve short codes

        hashed = hashlib.sha256(value.encode()).hexdigest()
        return hashed[: len(value) if len(value) < 16 else 16]

    # Lists: recursively anonymize
    if isinstance(value, list):
        return [anonymize_value(item, key) for item in value]

    # Dictionaries: recursively anonymize
    if isinstance(value, dict):
        return {k: anonymize_value(v, k) for k, v in value.items()}

    # Unknown types: convert to string representation
    return str(type(value).__name__)


def extract_schema(data: Any, path: str = "$") -> dict[str, Any]:
    """Extract schema structure from data.

    Args:
        data: The data to extract schema from
        path: JSON path to current location

    Returns:
        Schema dict with type, structure, and metadata
    """
    if data is None:
        return {"type": "null", "path": path}

    if isinstance(data, bool):
        return {"type": "boolean", "path": path}

    if isinstance(data, int):
        return {"type": "integer", "path": path}

    if isinstance(data, float):
        return {"type": "number", "path": path}

    if isinstance(data, str):
        schema: dict[str, Any] = {"type": "string", "path": path}

        # Detect format patterns
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", data):
            schema["format"] = "date-time"
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", data):
            schema["format"] = "date"
        elif "@" in data:
            schema["format"] = "email"
        elif re.match(r"^\d{10,}$", data):
            schema["format"] = "numeric-id"

        return schema

    if isinstance(data, list):
        schema = {"type": "array", "path": path, "length": len(data), "items": {}}

        # Sample first item for schema (if exists)
        if data:
            schema["items"] = extract_schema(data[0], f"{path}[0]")

        return schema

    if isinstance(data, dict):
        schema = {
            "type": "object",
            "path": path,
            "properties": {},
            "required": list(data.keys()),
        }

        for key, value in data.items():
            schema["properties"][key] = extract_schema(value, f"{path}.{key}")

        return schema

    return {"type": "unknown", "python_type": type(data).__name__, "path": path}


def compare_schemas(
    old_schema: dict[str, Any], new_schema: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compare two schemas and return differences.

    Args:
        old_schema: Previous schema version
        new_schema: Current schema version

    Returns:
        List of differences with change type and details
    """
    differences = []

    def compare_recursive(old: dict[str, Any], new: dict[str, Any], path: str) -> None:
        """Recursively compare schema structures."""
        # Type change
        if old.get("type") != new.get("type"):
            differences.append(
                {
                    "type": "TYPE_CHANGE",
                    "path": path,
                    "old_type": old.get("type"),
                    "new_type": new.get("type"),
                    "severity": "high",
                }
            )
            return  # Don't continue if types are different

        schema_type = old.get("type")

        # Object property changes
        if schema_type == "object":
            old_props = set(old.get("properties", {}).keys())
            new_props = set(new.get("properties", {}).keys())

            # New properties
            for prop in new_props - old_props:
                differences.append(
                    {
                        "type": "PROPERTY_ADDED",
                        "path": f"{path}.{prop}",
                        "severity": "low",
                    }
                )

            # Removed properties
            for prop in old_props - new_props:
                differences.append(
                    {
                        "type": "PROPERTY_REMOVED",
                        "path": f"{path}.{prop}",
                        "severity": "high",
                    }
                )

            # Compare common properties
            for prop in old_props & new_props:
                compare_recursive(
                    old["properties"][prop], new["properties"][prop], f"{path}.{prop}"
                )

        # Array item changes
        elif schema_type == "array":
            if "items" in old and "items" in new:
                compare_recursive(old["items"], new["items"], f"{path}[]")

        # Format changes for strings
        elif schema_type == "string":
            old_format = old.get("format")
            new_format = new.get("format")
            if old_format != new_format:
                differences.append(
                    {
                        "type": "FORMAT_CHANGE",
                        "path": path,
                        "old_format": old_format,
                        "new_format": new_format,
                        "severity": "medium",
                    }
                )

    compare_recursive(old_schema, new_schema, "$")
    return differences


class SchemaExtractor:
    """Extract and manage API schemas with anonymization."""

    def __init__(self, output_dir: str = "schemas"):
        """Initialize schema extractor.

        Args:
            output_dir: Directory to store schema files
        """
        self.output_dir = output_dir
        self.schemas: dict[str, dict[str, Any]] = {}
        self.anonymized_data: dict[str, Any] = {}
        self.metadata: dict[str, Any] = {}

    def register_endpoint(
        self, endpoint_name: str, data: Any, anonymize: bool = True
    ) -> None:
        """Register data from an API endpoint.

        Args:
            endpoint_name: Unique identifier for this endpoint
            data: Raw data from the endpoint
            anonymize: Whether to anonymize the data
        """
        # Extract schema
        schema = extract_schema(data)
        self.schemas[endpoint_name] = schema

        # Store anonymized data
        if anonymize:
            self.anonymized_data[endpoint_name] = anonymize_value(data)
        else:
            self.anonymized_data[endpoint_name] = data

    def save_schemas(self, filename: str = "api_schemas.json") -> None:
        """Save all schemas to a file.

        Args:
            filename: Output filename
        """
        os.makedirs(self.output_dir, exist_ok=True)

        output = {
            "generated_at": datetime.now().isoformat(),
            "metadata": self.metadata,
            "schemas": self.schemas,
            "anonymized_samples": self.anonymized_data,
        }

        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as file_obj:
            json.dump(output, file_obj, indent=2, default=str)

    def compare_with_previous(self, previous_file: str) -> list[dict[str, Any]]:
        """Compare current schemas with a previous version.

        Args:
            previous_file: Path to previous schema file

        Returns:
            List of all differences found
        """
        with open(previous_file, "r", encoding="utf-8") as file_obj:
            previous_data = json.load(file_obj)

        all_differences = []

        # Check each endpoint
        for endpoint_name, current_schema in self.schemas.items():
            if endpoint_name in previous_data["schemas"]:
                diffs = compare_schemas(
                    previous_data["schemas"][endpoint_name], current_schema
                )
                for diff in diffs:
                    diff["endpoint"] = endpoint_name
                    all_differences.append(diff)
            else:
                all_differences.append(
                    {
                        "type": "ENDPOINT_ADDED",
                        "endpoint": endpoint_name,
                        "severity": "low",
                    }
                )

        # Check for removed endpoints
        for endpoint_name in previous_data["schemas"]:
            if endpoint_name not in self.schemas:
                all_differences.append(
                    {
                        "type": "ENDPOINT_REMOVED",
                        "endpoint": endpoint_name,
                        "severity": "high",
                    }
                )

        return all_differences
