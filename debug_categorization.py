"""
Debugging tool for procedure categorization.

This script allows you to test how procedures are categorized by the case parser.
It uses the same backend logic as the main parser and shows you why a specific
category was chosen.

Usage:
    python debug_categorization.py "CABG with CPB" "CARDIAC SURGERY"
    python debug_categorization.py "AVR" "CARDIAC"
    python debug_categorization.py --interactive
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.case_parser.patterns.categorization import (
    categorize_cardiac,
    categorize_intracerebral,
    categorize_obgyn,
    categorize_procedure,
    categorize_vascular,
)
from src.case_parser.patterns.procedure_patterns import PROCEDURE_RULES

console = Console()


def debug_categorization(procedure: str, services_input: str) -> None:
    """
    Debug procedure categorization and show matching logic.

    Args:
        procedure: The procedure description
        services_input: Service names (comma or newline separated)
    """
    # Header
    console.print()
    console.print(
        Panel(
            "[bold cyan]Procedure Categorization Debug[/bold cyan]",
            border_style="cyan",
        )
    )

    # Parse services
    services = [
        s.strip() for s in services_input.replace(",", "\n").split("\n") if s.strip()
    ]

    # Input summary
    console.print()
    console.print("[bold]Input:[/bold]")
    console.print(f"  Procedure: [yellow]{procedure}[/yellow]")
    console.print(f"  Services:  [yellow]{', '.join(services)}[/yellow]")

    procedure_upper = procedure.upper()

    # Get the actual categorization result
    final_category, warnings = categorize_procedure(procedure, services)

    # Show matching trace
    console.print()
    console.print("[bold]Rule Matching Trace:[/bold]")

    matched_rules = []

    # Check each service
    for service in services:
        service_upper = service.upper()

        # Create table for this service
        table = Table(
            title=f"Service: {service}", show_header=True, header_style="bold magenta"
        )
        table.add_column("Rule #", style="dim", width=8)
        table.add_column("Category", style="cyan")
        table.add_column("Match Details", style="green")
        table.add_column("Result", style="yellow")

        # Check standard rules
        for idx, rule in enumerate(PROCEDURE_RULES, 1):
            keyword_matches = [kw for kw in rule.keywords if kw in service_upper]
            procedure_keyword_matches = [
                kw for kw in rule.keywords if kw in procedure_upper
            ]

            if keyword_matches or procedure_keyword_matches:
                # Build match details
                details = []
                if keyword_matches:
                    details.append(f"Service: {', '.join(keyword_matches)}")
                if procedure_keyword_matches:
                    details.append(f"Procedure: {', '.join(procedure_keyword_matches)}")

                # Check exclusions
                if rule.exclude_keywords:
                    excl_in_service = [
                        excl for excl in rule.exclude_keywords if excl in service_upper
                    ]
                    excl_in_procedure = [
                        excl
                        for excl in rule.exclude_keywords
                        if excl in procedure_upper
                    ]

                    if excl_in_service or excl_in_procedure:
                        excl_details = []
                        if excl_in_service:
                            excl_details.append(
                                f"Service: {', '.join(excl_in_service)}"
                            )
                        if excl_in_procedure:
                            excl_details.append(
                                f"Procedure: {', '.join(excl_in_procedure)}"
                            )
                        table.add_row(
                            f"#{idx}",
                            rule.category,
                            "\n".join(details),
                            f"[red]EXCLUDED[/red]\n{'; '.join(excl_details)}",
                        )
                        continue

                # Show subcategorization
                result_text = rule.category
                if rule.category == "Cardiac":
                    subcat = categorize_cardiac(procedure_upper)
                    result_text = f"[bold green]{subcat.value}[/bold green]"
                elif rule.category == "Procedures Major Vessels":
                    subcat = categorize_vascular(procedure)
                    result_text = f"[bold green]{subcat.value}[/bold green]"
                elif rule.category == "Intracerebral":
                    subcat = categorize_intracerebral(procedure)
                    result_text = f"[bold green]{subcat.value}[/bold green]"
                else:
                    result_text = f"[green]{result_text}[/green]"

                table.add_row(
                    f"#{idx}",
                    rule.category,
                    "\n".join(details),
                    result_text,
                )
                matched_rules.append(rule.category)
                break

        # Check OB/GYN special handling
        if any(kw in service_upper for kw in ("GYN", "OB", "OBSTET")):
            obgyn_cat = categorize_obgyn(procedure_upper)
            table.add_row(
                "Special",
                "OB/GYN",
                "Service contains GYN/OB/OBSTET",
                f"[bold green]{obgyn_cat.value}[/bold green]",
            )
            matched_rules.append(f"OB/GYN-{obgyn_cat.value}")

        if table.row_count > 0:
            console.print(table)

    # Final result
    console.print()
    result_panel = Panel(
        f"[bold green]{final_category.value}[/bold green]",
        title="[bold]Final Category[/bold]",
        border_style="green",
    )
    console.print(result_panel)

    # Warnings
    if warnings:
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for warning in warnings:
            console.print(f"  [yellow]⚠[/yellow]  {warning}")

    # Special cases
    if (
        "LABOR EPIDURAL" in procedure_upper
        and final_category.value == "Vaginal del"
        and not any("OB" in r or "GYN" in r for r in matched_rules)
    ):
        console.print()
        console.print(
            "[dim italic]Note: Labor epidural fallback applied (no OB/GYN service)"
            "[/dim italic]"
        )

    console.print()


def interactive_mode() -> None:
    """Run in interactive mode for multiple tests."""
    console.print(
        Panel(
            "[bold cyan]Interactive Procedure Categorization Debugger[/bold cyan]\n"
            "Type [yellow]'quit'[/yellow] or [yellow]'exit'[/yellow] to stop",
            border_style="cyan",
        )
    )
    console.print()

    while True:
        console.print("[dim]" + "─" * 80 + "[/dim]")
        try:
            procedure = console.input(
                "[bold]Enter procedure description:[/bold] "
            ).strip()
            if procedure.lower() in {"quit", "exit", "q"}:
                break

            services = console.input(
                "[bold]Enter service(s) (comma-separated):[/bold] "
            ).strip()
            if services.lower() in {"quit", "exit", "q"}:
                break

            console.print()
            debug_categorization(procedure, services)
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting...[/yellow]")
            break

    console.print()
    console.print("[green]Goodbye![/green]")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Debug procedure categorization logic",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a single categorization
  python debug_categorization.py "CABG with CPB" "CARDIAC SURGERY"

  # Test with multiple services
  python debug_categorization.py "AVR" "CARDIAC,THORACIC"

  # Interactive mode
  python debug_categorization.py --interactive
        """,
    )

    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Run in interactive mode",
    )

    parser.add_argument(
        "procedure",
        nargs="?",
        help="Procedure description",
    )

    parser.add_argument(
        "services",
        nargs="?",
        help="Service name(s) - comma or newline separated",
    )

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
    elif args.procedure and args.services:
        debug_categorization(args.procedure, args.services)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
