#!/usr/bin/env python3
"""Extract API schemas from Hydro-Québec portal for monitoring.

This script connects to the Hydro-Québec API, fetches data from all endpoints,
extracts the schema structure, anonymizes sensitive data, and saves everything
for future comparison.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from hydroqc.schema_extractor import SchemaExtractor
from hydroqc.webuser import WebUser


async def extract_all_schemas(
    username: str,
    password: str,
    customer_id: str,
    account_id: str,
    contract_id: str,
    output_dir: str = "schemas/latest",
) -> SchemaExtractor:
    """Extract schemas from all API endpoints.

    Args:
        username: Hydro-Québec username
        password: Hydro-Québec password
        customer_id: Customer ID to use
        account_id: Account ID to use
        contract_id: Contract ID to use
        output_dir: Directory to save schemas

    Returns:
        SchemaExtractor with all registered endpoints
    """
    extractor = SchemaExtractor(output_dir)

    # Create webuser
    webuser = WebUser(
        username,
        password,
        verify_ssl=True,
        log_level="ERROR",  # Quiet operation
    )

    try:
        print("Logging in...")
        await webuser.login()

        print("Fetching user info...")
        user_info = await webuser._hydro_client.get_user_info()
        extractor.register_endpoint("user_info", user_info)

        print("Fetching webuser info...")
        await webuser.get_info()

        print("Fetching customers...")
        await webuser.fetch_customers_info()

        # Get selected customer/account/contract (or use first if not specified)
        if customer_id:
            customer = webuser.get_customer(customer_id)
        else:
            customer = webuser.customers[0]
            print(f"Using customer: {customer.customer_id}")

        # Fetch customer data directly from API
        customer_data = await webuser._hydro_client.get_customer_info(
            customer.applicant_id, customer.customer_id
        )
        extractor.register_endpoint("customer_info", customer_data)

        if account_id:
            account = customer.get_account(account_id)
        else:
            account = customer.accounts[0]
            print(f"Using account: {account.account_id}")

        if contract_id:
            contract = account.get_contract(contract_id)
        else:
            contract = account.contracts[0]
            print(f"Using contract: {contract.contract_id}")

        print("Fetching contract info...")
        contract_info = await contract.get_info()
        extractor.register_endpoint("contract_info", contract_info)

        print("Fetching periods info...")
        periods_info = await contract.get_periods_info()
        extractor.register_endpoint("periods_info", periods_info)

        print("Fetching outages...")
        await contract.refresh_outages()
        if hasattr(contract, "_outages_data") and contract._outages_data:
            extractor.register_endpoint("outages", contract._outages_data)

        # Hourly consumption
        print("Fetching hourly consumption...")
        try:
            yesterday = date.today() - timedelta(days=1)
            hourly = await contract.get_hourly_consumption(yesterday)
            extractor.register_endpoint("hourly_consumption", hourly)
        except Exception as e:
            print(f"  Warning: Could not fetch hourly consumption: {e}")

        # Daily consumption
        print("Fetching daily consumption...")
        try:
            daily = await contract.get_today_daily_consumption()
            extractor.register_endpoint("daily_consumption", daily)
        except Exception as e:
            print(f"  Warning: Could not fetch daily consumption: {e}")

        # Monthly consumption
        print("Fetching monthly consumption...")
        try:
            monthly = await contract.get_monthly_consumption()
            extractor.register_endpoint("monthly_consumption", monthly)
        except Exception as e:
            print(f"  Warning: Could not fetch monthly consumption: {e}")

        # Annual consumption
        print("Fetching annual consumption...")
        try:
            annual = await contract.get_annual_consumption()
            extractor.register_endpoint("annual_consumption", annual)
        except Exception as e:
            print(f"  Warning: Could not fetch annual consumption: {e}")

        # Rate-specific endpoints
        if contract.rate == "DPC":
            print("Fetching DPC data...")
            try:
                dpc_data = await contract.get_dpc_data()
                extractor.register_endpoint("dpc_data", dpc_data)

                peak_data = await contract._hydro_client.get_dpc_peak_data(
                    contract.applicant_id, contract.customer_id, contract.contract_id
                )
                extractor.register_endpoint("dpc_peak_data", peak_data)
            except Exception as e:
                print(f"  Warning: Could not fetch DPC data: {e}")

        elif contract.rate == "D" and contract.rate_option == "CPC":
            print("Fetching CPC data...")
            try:
                cpc_data = await contract._hydro_client.get_cpc_credit(
                    contract.applicant_id, contract.customer_id, contract.contract_id
                )
                extractor.register_endpoint("cpc_data", cpc_data)
            except Exception as e:
                print(f"  Warning: Could not fetch CPC data: {e}")

        print(f"\nExtracted {len(extractor.schemas)} endpoint schemas")

    finally:
        await webuser.close_session()

    # Add metadata about the contract (with anonymized IDs)
    from hydroqc.schema_extractor import anonymize_value

    extractor.metadata = {
        "rate": contract.rate,
        "rate_option": contract.rate_option if contract.rate_option else "NONE",
        "customer_id": anonymize_value(customer.customer_id, "customer_id"),
        "account_id": anonymize_value(account.account_id, "account_id"),
        "contract_id": anonymize_value(contract.contract_id, "contract_id"),
    }

    return extractor


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Extract API schemas from Hydro-Québec portal"
    )
    parser.add_argument("-u", "--username", help="Hydro-Québec username")
    parser.add_argument("-p", "--password", help="Hydro-Québec password")
    parser.add_argument("-c", "--customer", help="Customer ID")
    parser.add_argument("-a", "--account", help="Account ID")
    parser.add_argument("-C", "--contract", help="Contract ID")
    parser.add_argument(
        "-o",
        "--output-dir",
        default="schemas/latest",
        help="Output directory (default: schemas/latest)",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Also save to archive with timestamp",
    )

    args = parser.parse_args()

    # Try environment variables if not provided
    if not args.username:
        args.username = os.environ.get("HYDROQC_0_USERNAME")
    if not args.password:
        args.password = os.environ.get("HYDROQC_0_PASSWORD")
    if not args.customer:
        args.customer = os.environ.get("HYDROQC_0_CUSTOMER_NUMBER")
    if not args.account:
        # Try to extract from diagnostic or prompt
        pass
    if not args.contract:
        # Try to extract from diagnostic or prompt
        pass

    # Validate required args
    if not all([args.username, args.password]):
        parser.error("Username and password required (via args or environment)")

    return args


async def main() -> int:
    """Main entry point."""
    args = parse_args()

    try:
        # Extract schemas
        extractor = await extract_all_schemas(
            args.username,
            args.password,
            args.customer,
            args.account,
            args.contract,
            args.output_dir,
        )

        # Save to latest
        print(f"\nSaving schemas to {args.output_dir}/api_schemas.json")
        extractor.save_schemas()

        # Also save to archive if requested
        if args.archive:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            archive_dir = "schemas/archive"
            os.makedirs(archive_dir, exist_ok=True)
            archive_path = os.path.join(archive_dir, f"{timestamp}_api_schemas.json")
            print(f"Archiving to {archive_path}")
            output = {
                "generated_at": datetime.now().isoformat(),
                "metadata": extractor.metadata,
                "schemas": extractor.schemas,
                "anonymized_samples": extractor.anonymized_data,
            }
            with open(archive_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, default=str)

        print("\n✅ Schema extraction complete!")
        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
