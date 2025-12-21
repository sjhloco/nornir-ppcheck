import argparse
import sys
from typing import TYPE_CHECKING, Any

from nornir import InitNornir
from nornir.core.filter import F
from nornir_rich.functions import print_inventory  # type: ignore
from rich.console import Console
from rich.theme import Theme

if TYPE_CHECKING:
    from nornir.core import Nornir


# ----------------------------------------------------------------------------
# BUILD_INV: Builds the Nornir inventory of groups and devices
# ----------------------------------------------------------------------------
class BuildInventory:
    def __init__(self) -> None:
        my_theme = {"repr.ipv4": "none", "repr.number": "none", "repr.call": "none"}
        self.rc = Console(theme=Theme(my_theme))

    # ----------------------------------------------------------------------------
    # 1. FLAGS: Optional runtime flags to filter inventory and override usernames
    # ----------------------------------------------------------------------------
    def add_arg_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-n",
            "--hostname",
            help="Hosts that contain any of this string in their name",
        )
        parser.add_argument(
            "-g",
            "--group",
            nargs="+",
            help="Filter hosts based on group membership which is the operating system (iosxe, nxos, palo, etc)",
        )
        parser.add_argument(
            "-l",
            "--location",
            nargs="+",
            help="Filter hosts based on physical location",
        )
        parser.add_argument(
            "-ll",
            "--logical",
            nargs="+",
            help="Filter hosts based on logical location (WAN, WAN Edge, Core, Access, Services, etc)",
        )
        parser.add_argument(
            "-t",
            "--type",
            nargs="+",
            help="Filter hosts based on device types (firewall, router, dc_switch, switch, wifi_controller, etc)",
        )
        parser.add_argument(
            "-v",
            "--version",
            help="Hosts that contain any of this string in their software version",
        )
        parser.add_argument(
            "-s",
            "--show",
            action="store_true",
            help="Prints the inventory hosts matched by the filters",
        )
        parser.add_argument(
            "-sd",
            "--show_detail",
            action="store_true",
            help="Prints the inventory hosts matched by the filters including all their attributes",
        )
        return parser

    # LOAD_INV: Creates inventory from static files
    def load_inventory(self, hosts: str, groups: str) -> Nornir:
        nr: Nornir = InitNornir(
            inventory={
                "plugin": "SimpleInventory",
                "options": {"host_file": hosts, "group_file": groups},
            }
        )
        return nr

    # ----------------------------------------------------------------------------
    # 2 FILTER_INV: Filters the host in the inventory  based on any arguments passed
    # ----------------------------------------------------------------------------
    def filter_inventory(self, args: dict[str, Any], nr: Nornir) -> Nornir:
        filters = []
        if args.get("hostname") is not None:
            list_hosts = args["hostname"].split()
            for _n in range(10 - len(list_hosts)):
                list_hosts.append("DUMMY")
            nr = nr.filter(
                F(name__contains=list_hosts[0])
                | F(name__contains=list_hosts[1])
                | F(name__contains=list_hosts[2])
                | F(name__contains=list_hosts[3])
                | F(name__contains=list_hosts[4])
                | F(name__contains=list_hosts[5])
                | F(name__contains=list_hosts[6])
                | F(name__contains=list_hosts[7])
                | F(name__contains=list_hosts[8])
                | F(name__contains=list_hosts[9])
            )
            filters.append(args["hostname"])
        if args.get("group") is not None:
            nr = nr.filter(F(groups__any=args["group"]))
            filters.extend(args["group"])
        if args.get("location") is not None:
            nr = nr.filter(F(Infra_Location__any=args["location"]))
            filters.extend(args["location"])
        if args.get("logical") is not None:
            nr = nr.filter(F(Infra_Logical_Location__any=args["logical"]))
            filters.extend(args["logical"])
        if args.get("type") is not None:
            nr = nr.filter(F(type__any=args["type"]))
            filters.extend(args["type"])
        if args.get("version") is not None:
            nr = nr.filter(F(IOSVersion__contains=args["version"]))
            filters.append(args["version"])

        # Print and exit if show or show_detail flags set
        num_hosts = len(nr.inventory.hosts.items())
        if args.get("show", False):
            self.rc.print("[blue]=[/blue]" * 70)
            self.rc.print(
                f"[i cyan]{num_hosts}[/i cyan] hosts have matched the filters [i cyan]'{', '.join(filters)}'[/i cyan]:"
            )
            for each_host, data in nr.inventory.hosts.items():
                self.rc.print(
                    f"[green]-Host: {each_host}[/green]\t[red]=[/red]  Hostname: {data.hostname}"
                )
            sys.exit(0)
        elif args.get("show_detail", False):
            self.rc.print("[blue]=[/blue]" * 70)
            self.rc.print(
                f"[i cyan]{num_hosts}[/i cyan] hosts have matched the filters [i cyan]'{', '.join(filters)}'[/i cyan]:"
            )
            print_inventory(nr)
            sys.exit(0)
        else:
            return nr

    # ----------------------------------------------------------------------------
    # 3. DEFAULT_INV: Adds username and password to defaults of the inventory (fallback for all devices)
    # ----------------------------------------------------------------------------
    def inventory_defaults(self, nr: Nornir, device: dict[str, Any]) -> Nornir:
        nr.inventory.defaults.username = device["user"]
        nr.inventory.defaults.password = device["pword"]

        return nr
