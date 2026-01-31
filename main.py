import contextlib
import difflib
import getpass
import glob
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from deepmerge import always_merger
from nornir.core.task import Result, Task
from nornir_netmiko.tasks import netmiko_send_command  # type: ignore
from nornir_rich.functions import print_result  # type: ignore
from nornir_utils.plugins.tasks.files import write_file  # type: ignore
from rich.console import Console
from rich.theme import Theme

import nornir_inv

if TYPE_CHECKING:
    from nornir.core import Nornir

    from nornir_inv import BuildInventory


from nornir_validate import (
    generate_val_file,
    print_result_gvf,
    print_result_val,
    validate,
)

# ----------------------------------------------------------------------------
# VARIABLES: Hardcoded variables to allow for further customisation (mainly naming)
# ----------------------------------------------------------------------------
# Default username
default_user = "admin"
# Location of the nornir inventory file
inventory = (
    Path(os.getenv("BASE_DIRECTORY") or Path(__file__).parent.resolve()) / "inventory"
)
# Folder that stores reports and output saved to file
output_folder = "output"
# Folder that stores validation files
val_files_folder = "val_files"


# ----------------------------------------------------------------------------
# ENV VARS: Either set as env vars or fallback to defaults
# ----------------------------------------------------------------------------
# Location of the project folder, default is the current directory
BASE_DIRECTORY = Path(os.getenv("BASE_DIRECTORY") or Path(__file__).parent.resolve())
# Default device username (-u >> env_var >> admin)
DEVICE_USER = os.environ.get("DEVICE_USER", default_user)
# Default device password (env_var >> get_pass)
DEVICE_PWORD = os.environ.get("DEVICE_PWORD", None)
# File in project folder containing cmds to run (env_var >> project_dir/input_cmds.yml)
INPUT_CMD_FILE = os.environ.get("INPUT_CMD_FILE", "input_cmds.yml")
# File in project folder containing index to build validation file from (env_var >> project_dir/input_index.yml)
INPUT_INDEX_FILE = os.environ.get("INPUT_INDEX_FILE", "input_index.yml")


# ----------------------------------------------------------------------------
# 1. ARG/VALIDATE: Addition of input arguments and input file validation
# ----------------------------------------------------------------------------
class InputValidate:
    def __init__(self) -> None:
        my_theme = {"repr.ipv4": "none", "repr.number": "none", "repr.call": "none"}
        self.rc = Console(theme=Theme(my_theme))

    # ----------------------------------------------------------------------------
    # HELPER: Errors and exits if files are missing (input or compare).
    # ----------------------------------------------------------------------------
    def _err_missing_files(self, run_type: str, missing_files: list) -> None:
        if len(missing_files) != 0:
            files = ", ".join(missing_files)
            self.rc.print(f":x: The '{run_type}' file {files} does not exist")
            sys.exit(1)

    # ----------------------------------------------------------------------------
    # HELPER: Get Path for output folder, if it doesn't already exist creates it.
    # ----------------------------------------------------------------------------
    def _get_output_fldr(self, run_type: str, file_path: str) -> Path:
        working_dir = BASE_DIRECTORY / file_path
        if not working_dir.exists():
            self.rc.print(
                f":x: The '{run_type}' working directory {str(working_dir)} does not exist"
            )
            sys.exit(1)
        output_fldr = working_dir / output_folder
        # Create output folder if doesn't exist
        output_fldr.mkdir(parents=True, exist_ok=True)
        return output_fldr

    # ----------------------------------------------------------------------------
    # HELPER: Get Path for validation files folder, if it doesn't already exist creates it.
    # ----------------------------------------------------------------------------
    def _get_val_files_fldr(self, run_type: str, file_path: str | Path) -> Path:
        working_dir = BASE_DIRECTORY / file_path
        if not working_dir.exists():
            self.rc.print(
                f":x: The '{run_type}' working directory {str(working_dir)} does not exist"
            )
            sys.exit(1)
        val_files_fldr = working_dir / val_files_folder
        # Create validation files folder if doesn't exist
        val_files_fldr.mkdir(parents=True, exist_ok=True)
        return val_files_fldr

    # ----------------------------------------------------------------------------
    # HELPER: Validates input files contents are of the correct format (structure).
    # ----------------------------------------------------------------------------
    def _val_input_file(
        self, run_type: str, input_file: str, input_data: dict[str, Any]
    ) -> None:
        if input_data is None:
            self.rc.print(f":x: The '{run_type}' input file {input_file} is empty")
            sys.exit(1)
        required_keys = any(
            isinstance(input_data.get(key), dict) for key in ("hosts", "groups", "all")
        )
        if not required_keys:
            self.rc.print(
                f":x: {input_file} must have at least one [i]hosts, groups[/i] or [i]all[/i] dictionary"
            )
            sys.exit(1)

    # ----------------------------------------------------------------------------
    # HELPER: Ensures is at least one val file in val_files folder, if more than 1 merges them into one file
    # ----------------------------------------------------------------------------
    def _get_merge_val_files(self, val_files_fldr: Path) -> dict[str, dict[str, Any]]:
        input_data: dict[str, dict[str, Any]] = {"all": {}, "groups": {}, "hosts": {}}

        # FILES: Gather all files in val_files folder or error if none:
        all_files = list(Path(val_files_fldr).glob("*.yml"))
        if not all_files:
            print(f"❌ There are no .yml validation files in {val_files_fldr}")
            sys.exit(1)

        for file_path in all_files:
            with open(file_path) as f:
                tmp_data = yaml.load(f, Loader=yaml.FullLoader)
            # ERR: Errors based on whether input file correctly formatted
            self._val_input_file("validate", str(file_path), tmp_data)

            # MERGE: Deepmerge handles the merging of all, hosts, and groups sections
            if "all" in tmp_data:
                # ALL: Direct merge for 'all' section - modifies target in place (is only 1 top layer dict)
                always_merger.merge(input_data["all"], tmp_data["all"])
            # HST/GRP: Merge each sub-group, nested dict of grp_name or host_name
            for section in ("hosts", "groups"):
                if section in tmp_data:
                    for sec_name, feat in tmp_data[section].items():
                        if sec_name not in input_data[section]:
                            input_data[section][sec_name] = feat
                        else:
                            always_merger.merge(input_data[section][sec_name], feat)
        # Verify that is data in at least one section from the files
        if all(len(input_data[key]) == 0 for key in ("all", "groups", "hosts")):
            print(
                f"❌ None of the validation files in {val_files_fldr} have all, groups or hosts dictionaries"
            )
            sys.exit(1)

        return input_data

    # ----------------------------------------------------------------------------
    # 1a. ARGS: Processes run time flags and arguments, adds these additional args to those from nornir_inv.py.
    # ----------------------------------------------------------------------------
    def add_arg_parser(self, nr_inv_args: BuildInventory) -> dict[str, Any]:
        args = nr_inv_args.add_arg_parser()
        args.add_argument(
            "-u",
            "--username",
            help="Device username, overrides environment variables and hardcoded script variable",
        )
        args.add_argument(
            "-prt",
            "--print",
            nargs=1,
            help="Name of change directory or direct path to input file",
        )
        args.add_argument(
            "-vtl",
            "--vital_save",
            nargs=1,
            help="Name of change directory where to save files created from vital command outputs",
        )
        args.add_argument(
            "-dtl",
            "--detail_save",
            nargs=1,
            help="Name of change directory where to save files created from detail command outputs",
        )
        args.add_argument(
            "-cmp",
            "--compare",
            nargs=3,
            help="Name of directory that holds compare files (where compare output is saved) as well the name of the files to compare",
        )
        args.add_argument(
            "-pre",
            "--pre_test",
            nargs=1,
            help="Name of change directory, runs print, vital_save_file and detail_save_file",
        )
        args.add_argument(
            "-pos",
            "--post_test",
            nargs=1,
            help="Name of change directory, runs print, vital_save_file and compare (of vital)",
        )
        args.add_argument(
            "-gvf",
            "--gen_val_file",
            nargs=1,
            help="Name of change directory where index file is and validation input files will be saved",
        )
        args.add_argument(
            "-val",
            "--validate",
            nargs=1,
            help="Name of change directory (where val file is and to save compliance report) or direct path to validation input file",
        )
        return vars(args.parse_args())

    # ----------------------------------------------------------------------------
    # 1b. RUNTYPE: Filters all non inventory runtime {flags:args} to only those used (not false).
    # ----------------------------------------------------------------------------
    def get_run_type(self, args: dict[str, Any]) -> tuple[str | None, list[str]]:
        run_type = None
        file_path = []
        wanted_args = [
            "print",
            "vital_save",
            "detail_save",
            "compare",
            "validate",
            "gen_val_file",
            "pre_test",
            "post_test",
        ]
        # Get just wanted_args from args
        tmp_args = {k: v for k, v in args.items() if k in wanted_args}
        # If chooses wanted_arg if it has an arg (path or file name) from runtime
        for k, v in tmp_args.items():
            if v is not None:
                run_type = k
                file_path = v
        return run_type, file_path

    # ----------------------------------------------------------------------------
    # 1c. COMPARE: For 'compare' gather full Path for directory and the compare files, validating all exist (a list of 3 elements, output_fldr & 2 compare files).
    # ----------------------------------------------------------------------------
    def compare_arg(self, file_path: list[str]) -> dict[str, Path]:
        missing_files = []
        # PATH: Get full path for output folder to store command and diff files
        output_fldr = self._get_output_fldr("compare", file_path[0])
        # ERR/RTR: Errors or returns file paths based on whether exist or not
        cmp_file1 = output_fldr.parent / file_path[1]
        cmp_file2 = output_fldr.parent / file_path[2]
        for cmp_file in [cmp_file1, cmp_file2]:
            if not cmp_file.exists():
                missing_files.append(str(cmp_file))
        self._err_missing_files("compare", missing_files)

        return dict(output_fldr=output_fldr, cmp_file1=cmp_file1, cmp_file2=cmp_file2)

    # ----------------------------------------------------------------------------
    # 1d. NOT_COMPARE: For all other runtime args (except validate) gather/ validate working dir path, load input file and validate contents.
    # ----------------------------------------------------------------------------
    def noncompare_arg(self, run_type: str, file_path: list[str]) -> dict[str, Any]:
        # PRT: If is 'print' and a single input file (not directory) create input and output file path (output wont be used)
        if run_type == "print" and file_path[0].endswith((".yml", ".yaml")):
            input_file = Path(file_path[0])
            output_fldr = input_file.parent / output_folder
        # ALL_OTHER: Get full path for input and output folders (to store command and diff files)
        else:
            output_fldr = self._get_output_fldr(run_type, file_path[0])
            input_file = output_fldr.parent / INPUT_CMD_FILE
        # ERR/RTR: Errors or returns file paths based on whether input file correctly formatted
        if not input_file.exists():
            self._err_missing_files(run_type, [str(input_file)])
        elif input_file.exists():
            with open(input_file) as file_content:
                input_data = yaml.load(file_content, Loader=yaml.FullLoader)
            self._val_input_file(run_type, str(input_file), input_data)

        return dict(
            output_fldr=output_fldr, input_file=input_file, input_data=input_data
        )

    # ----------------------------------------------------------------------------
    # 1e. VAL: For gen_val_file/validate gather and validate working dir path, load input files and validate contents.
    # ----------------------------------------------------------------------------
    def val_arg(self, run_type: str, file_path: list[str]) -> dict[str, Any]:
        # FULL_PATH: If full path for index or validate file create file and folder path variables (output for val to save reports, val for gvf to save val files)
        if file_path[0].endswith((".yml", ".yaml")):
            input_file = Path(file_path[0])
            output_fldr = Path("/dev/null")  # Doesn't need output folder
            if run_type == "gen_val_file":
                val_files_fldr = self._get_val_files_fldr(
                    run_type, str(input_file.parent)
                )
            elif run_type == "validate":
                val_files_fldr = Path("/dev/null")  # Doesn't need val files folder

            # ERR/LOAD: Loads input file and checks that its contents are correctly formatted
            if not input_file.exists():
                self._err_missing_files(run_type, [str(input_file)])
            elif input_file.exists():
                with open(input_file) as file_content:
                    input_data = yaml.load(file_content, Loader=yaml.FullLoader)
                self._val_input_file(run_type, str(input_file), input_data)

        # GVF_DIR: If directory and GVF create file and val_file folder path variables (dont need output folder so dummy), if no index file runs with nornir-validate default
        elif run_type == "gen_val_file":
            val_files_fldr = self._get_val_files_fldr(run_type, file_path[0])
            output_fldr = Path("/dev/null")  # Dummy path as not used in gvf
            input_file = val_files_fldr.parent / INPUT_INDEX_FILE
            # ERR/LOAD: If input file exists loads and that its contents are correctly formatted, if not exist returns empty dict to run with nornir-validate default
            if input_file.exists():
                with open(input_file) as file_content:
                    input_data = yaml.load(file_content, Loader=yaml.FullLoader)
                self._val_input_file(run_type, str(input_file), input_data)
            else:
                input_data = {}

        # VAL_DIR: If directory and VAL create output folder path variables
        else:
            output_fldr = self._get_output_fldr(run_type, file_path[0])
            val_files_fldr = self._get_val_files_fldr(run_type, file_path[0])
            input_data = self._get_merge_val_files(val_files_fldr)

        return dict(
            output_fldr=output_fldr,
            val_files_fldr=val_files_fldr,
            input_data=input_data,
        )

    # ----------------------------------------------------------------------------
    # 1f. USER_PASS: Gathers username/password checking various input options.
    # ----------------------------------------------------------------------------
    def get_user_pass(self, args: dict[str, Any]) -> dict[str, Any]:
        # USER: Check for username in this order: args (-u), env var, default_username (admin)
        device = {}
        if args.get("username") is not None:
            device["user"] = args["username"]
        else:
            device["user"] = DEVICE_USER
        # PWORD: Check for password in this order: env var, prompt
        if os.environ.get("DEVICE_PWORD") is not None:
            device["pword"] = os.environ["DEVICE_PWORD"]
        else:
            device["pword"] = getpass.getpass("Enter device password: ")
        return device


# ----------------------------------------------------------------------------
# 2. NORNIR_ENGINE: Uses nornir to run commands
# ----------------------------------------------------------------------------
class NornirEngine:
    def __init__(self, nr_inv: Nornir) -> None:
        self.nr_inv = nr_inv

    # ----------------------------------------------------------------------------
    # 2b. Command engine runs the sub-tasks to get commands and possibly save results to file
    # ----------------------------------------------------------------------------
    def cmd_engine(
        self, task: Task, data: dict[str, Any], run_type: str
    ) -> Result | None:
        # 3. NR_CMD: Instantiates NornirCommands, holds all the runable nornir tasks
        self.nr_cmd = NornirCommands()

        # ORG_CMD: Organises cmds to be run and also creates empty lists to store results
        result, empty_result = ([] for i in range(2))
        cmds = self.nr_cmd.organise_cmds(task, data.get("input_data", {}))

        # RUN_CFG: Saves running config to file
        if cmds["run_cfg"] and data["output_fldr"] is not None:
            result.append(
                self.nr_cmd.run_save_cmd(task, "config", data, cmds["run_cfg"])
            )
        # PRT: Prints command output to screen
        if run_type == "print":
            self.nr_cmd.run_print_cmd(task, cmds["print"])
        # VTL_DTL: Saves vital or detail commands to file
        elif run_type == "vital" or run_type == "detail":
            result.append(
                self.nr_cmd.run_save_cmd(task, run_type, data, cmds[run_type])
            )
        # CMP: Compares 2 specified files
        elif run_type == "compare":
            result.append(self.nr_cmd.create_diff("compare", data))

        # PRE/POST: Prints cmds to screen and saves vital commands to file
        else:
            self.nr_cmd.run_print_cmd(task, cmds["print"])
            result.append(self.nr_cmd.run_save_cmd(task, "vital", data, cmds["vital"]))
            # PRE: saves vital commands to file
            if run_type == "pre_test":
                result.append(
                    self.nr_cmd.run_save_cmd(task, "detail", data, cmds["detail"])
                )
            # POST: Compares 2 latest vital and config
            elif run_type == "post_test":
                result.append(
                    self.nr_cmd.pos_create_diff(task, "vital", data["output_fldr"])
                )
                if cmds["run_cfg"]:
                    result.append(
                        self.nr_cmd.pos_create_diff(task, "config", data["output_fldr"])
                    )

        # RESULT: Prints warning if no commands (for pre and post test) and/or file location for any saved files
        for each_type in ["print", "vital", "detail"]:
            if len(cmds[each_type]) == 0:
                empty_result.append(each_type)
        if not cmds["run_cfg"]:
            empty_result.append("config")
        if len(empty_result) != 0 and (
            run_type == "pre_test" or run_type == "post_test"
        ):
            empties = ", ".join(list(empty_result))
            result.append(f"⚠️  There were no commands to run for: {empties}")

        if len(result) != 0:
            # Removes dummy entries (labelled as 'empty') from not saving cmds to file
            with contextlib.suppress(ValueError):
                result.remove("empty")
            return Result(host=task.host, result="\n".join(result))
        else:
            return None

    # ----------------------------------------------------------------------------
    # 2a. Task engine to run nornir task for commands and prints result
    # ----------------------------------------------------------------------------
    def task_engine(self, run_type: str, data: dict[str, Any]) -> None:
        # 2a. Runs imported nonrir-validate tasks
        if run_type == "gen_val_file":
            # GVF without user defined input index file (uses nornir-validate default)
            if len(data["input_data"]) == 0:
                # result = self.nr_inv.run(task=generate_val_file)
                result = self.nr_inv.run(
                    name=f"{'Generate Validation Files'}",
                    task=generate_val_file,
                    directory=str(data["val_files_fldr"]),
                )
            # GVF with user defined index file
            else:
                result = self.nr_inv.run(
                    name=f"{'Generate Validation Files'}",
                    task=generate_val_file,
                    input_data=data["input_data"],
                    directory=str(data["val_files_fldr"]),
                )
            print_result_gvf(result, self.nr_inv)
            ## Use instead of 'print_result_gvf'` if troubleshooting 'gen_val_file'
            # from nornir_rich.functions import print_result
            # print_result(result)
        elif run_type == "validate":
            # EXACT_FILE: When validating exact file path pass/fail report printed to screen and not saved
            if str(data.get("output_fldr", "")) == "/dev/null":
                result = self.nr_inv.run(
                    name=f"{'Compliance Report'}",
                    task=validate,
                    input_data=data["input_data"],
                    print_report=True,
                )
            else:
                # VAL_FLDR: When using change_fldr/val_fldr of files saves report and only prints if it fails
                result = self.nr_inv.run(
                    name=f"{'Compliance Report'}",
                    task=validate,
                    input_data=data["input_data"],
                    save_report=str(data["output_fldr"]),
                )
            print_result_val(result)

        # 2b. The parent nornir task in which the cmd_engine runs the nornir sub-tasks
        else:
            run_type = run_type.replace("_save", "")
            result = self.nr_inv.run(
                name=f"{run_type.upper()} command output",
                task=self.cmd_engine,
                data=data,
                run_type=run_type,
            )
            # Only prints out result if commands where run against a device
            if result[list(result.keys())[0]].result != "Nothing run":
                # Uses my custom version of nornir-rich to delete empty results when run with prt flag
                print_result(result, vars=["result"], line_breaks=True)


# ----------------------------------------------------------------------------
# 3. Uses nornir to run commands
# ----------------------------------------------------------------------------
class NornirCommands:
    def __init__(self) -> None:
        pass

    # ----------------------------------------------------------------------------
    # CMDS: Creates a dictionary of the commands
    # ----------------------------------------------------------------------------
    def get_cmds(self, cmds: dict[str, Any], input_data: dict[str, Any]) -> None:
        cmds["run_cfg"] = cmds["run_cfg"] + input_data.get("run_cfg", False)
        cmds["print"].extend(input_data.get("cmd_print", []))
        cmds["vital"].extend(input_data.get("cmd_vital", []))
        cmds["detail"].extend(input_data.get("cmd_detail", []))
        self.cmds = cmds  # Needed so can unittest this method as no return

    # ----------------------------------------------------------------------------
    # ORG_CMD: Filters the commands based on the host got from nornir task
    # ----------------------------------------------------------------------------
    def organise_cmds(self, task: Task, input_data: dict[str, Any]) -> dict[str, Any]:
        cmds = dict(print=[], vital=[], detail=[], run_cfg=False)
        # If run_cfg is set gathers and saves that first before getting the rest of commands
        if input_data.get("all") is not None:
            self.get_cmds(cmds, input_data["all"])
        if input_data.get("groups") is not None:
            for each_grp in input_data["groups"]:
                if each_grp in task.host.groups:
                    self.get_cmds(cmds, input_data["groups"][each_grp])
        if input_data.get("hosts") is not None:
            for each_hst in input_data["hosts"]:
                if (
                    each_hst.lower() == str(task.host).lower()
                    or each_hst.lower() == str(task.host.hostname).lower()
                ):
                    self.get_cmds(cmds, input_data["hosts"][each_hst])
        if cmds["run_cfg"]:
            cmds["run_cfg"] = ["show running-config"]
        return cmds

    # ----------------------------------------------------------------------------
    # RUN_CMD: Runs a nornir task that executes a list of commands on a device
    # ----------------------------------------------------------------------------
    def run_cmds(self, task: Task, cmd: list, sev_level: int) -> str:
        all_output = ""
        for each_cmd in cmd:
            output = "==== " + each_cmd + " " + "=" * (79 - len(each_cmd)) + "\n"
            cmd_output = task.run(
                name=each_cmd,
                task=netmiko_send_command,
                command_string=each_cmd,
                severity_level=sev_level,
            ).result
            all_output = all_output + output + cmd_output + "\n\n\n"
        return all_output

    # ----------------------------------------------------------------------------
    # SAVE_CMD: Runs a nornir task to save cmd output (gathered by diff method) to file
    # ----------------------------------------------------------------------------
    def save_cmds(
        self, task: Task, run_type: str, data: dict[str, Any], output: str
    ) -> str:
        date = datetime.now().strftime("%Y%m%d-%H%M")
        file_name = str(task.host) + "_" + run_type + "_" + date + ".txt"
        output_file = os.path.join(data["output_fldr"], file_name)
        task.run(
            task=write_file,
            filename=output_file,
            content=output,
            severity_level=logging.DEBUG,
        )
        return output_file

    # ----------------------------------------------------------------------------
    # PRINT_CMD: Runs and prints the command outputs to screen
    # ----------------------------------------------------------------------------
    def run_print_cmd(self, task: Task, cmds: list) -> None:
        if len(cmds) != 0:
            self.run_cmds(task, cmds, logging.INFO)

    # ----------------------------------------------------------------------------
    # RUN_SAVE_CMD: Uses separate methods to runs and save the command outputs to file
    # ----------------------------------------------------------------------------
    def run_save_cmd(
        self, task: Task, run_type: str, data: dict[str, Any], cmds: list
    ) -> str:
        if len(cmds) != 0:
            output = ""
            output = self.run_cmds(task, cmds, logging.DEBUG)
            output_file = self.save_cmds(task, run_type, data, output)
            return f"✅ Created command output file '{output_file}'"
        return "empty"

    # ----------------------------------------------------------------------------
    # 3f. DIFF: Create HTML diff file from 2 input files
    # ----------------------------------------------------------------------------
    def create_diff(self, file_type: str, data: dict[str, Any]) -> str:
        # Create friendly names for report, new file names and load compare files
        pre_file_name = data["cmp_file1"].replace("\\", "/").split("/")[-1]
        post_file_name = data["cmp_file2"].replace("\\", "/").split("/")[-1]
        date = datetime.now().strftime("%Y%m%d-%H%M")
        tmp_name = (
            pre_file_name.split(file_type)[0]
            + "diff_"
            + file_type
            + "_"
            + date
            + ".html"
        )
        output_file = os.path.join(data["output_fldr"], tmp_name)
        with open(data["cmp_file1"]) as f:
            pre = f.readlines()
        with open(data["cmp_file2"]) as f:
            post = f.readlines()
        # Create diff html page with a reduced font size in the html table
        diff = difflib.HtmlDiff().make_file(pre, post, pre_file_name, post_file_name)
        diff_font = diff.replace("   <tbody>", '   <tbody style="font-size:12px">')
        with open(output_file, "w") as f:
            f.write(diff_font)
        return f"✅ Created compare HTML file '{output_file}'"

    # ----------------------------------------------------------------------------
    # 3g. POST_DIFF: Gets last 2 files and compares them
    # ----------------------------------------------------------------------------
    def pos_create_diff(self, task: Task, file_type: str, output_fldr: str) -> str:
        hostname = str(task.host)
        file_filter = os.path.join(output_fldr, hostname + "_" + file_type + "*")
        # Uses glob to match file names using a filter, then selects last 2 (most recent) to compare
        files = glob.glob(file_filter)
        files.sort(reverse=True)
        if len(files) >= 2:
            data = dict(output_fldr=output_fldr, cmp_file1=files[1], cmp_file2=files[0])
            return self.create_diff(file_type, data)
        else:
            return f"❌ Only {len(files)} file matched the filter '{file_filter}' for files to be compared"


# ----------------------------------------------------------------------------
# Engine that runs the methods from the script
# ----------------------------------------------------------------------------
def main() -> None:
    build_inv = nornir_inv.BuildInventory()  # parsers in nor_inv script
    input_val = InputValidate()  # parsers & val in this file

    # 1a. Gets info input by user by calling local method that calls remote nor_inv method
    args = input_val.add_arg_parser(build_inv)

    # 1b. Get the run type (flag used), provide user feedback if no runtime flag specified
    run_type, file_path = input_val.get_run_type(args)

    # 1e/f. VAL: Validate input or index files exist and are correct format, gets device creds
    if run_type == "gen_val_file" or run_type == "validate":
        data = input_val.val_arg(run_type, file_path)
        device = input_val.get_user_pass(args)

    # 1c. CMP: Validate directories and files exist, doesn't need device creds
    elif run_type == "compare":
        data = input_val.compare_arg(file_path)
        device = dict(user=None, pword=None)
    # 1d/f. OTHER: Validates the input file exists, is correct format and gets device creds
    elif run_type is not None:
        data = input_val.noncompare_arg(run_type, file_path)
        device = input_val.get_user_pass(args)

    # Loads inventory using static host and group files (checks first if location changed with env vars)
    nr_inv = build_inv.load_inventory(
        os.path.join(os.environ.get("INVENTORY", inventory), "hosts.yml"),
        os.path.join(os.environ.get("INVENTORY", inventory), "groups.yml"),
    )

    # Filter the inventory based on the runtime flags and add creds to Nornir inventory defaults
    nr_inv = build_inv.filter_inventory(args, nr_inv)
    nr_inv = build_inv.inventory_defaults(nr_inv, device)

    # 2a. Run the nornir tasks dependant on the run type (runtime flag)
    nr_eng = NornirEngine(nr_inv)
    if run_type is not None:
        nr_eng.task_engine(run_type, data)


if __name__ == "__main__":
    main()
