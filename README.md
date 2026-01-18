# Nornir Pre/Post Checks

The idea behind this project is to gather the facts (command outputs) about the network state before and after a change and compare the results. There are 3 different command outputs that we are interested in for this purpose:

- **Print:** Outputs printed to screen so we can eyeball the network state before the change
- **vital:** Outputs to compare after the change, will likely be some overlap with the print commands
- **detail:** Outputs only really needed if we have issues after a change (for example full ARP or MAC table)

*Nornir* is used to gather the command output with the scope of devices being based on a static inventory and pre-built filters. The inventory is defined in its own module (*nornir_inv.py*) with the idea being that it will make it easier to swap out for a dynamic inventory plugin if need be.

This project also incorporates [nornir-validate](https://github.com/sjhloco/nornir-validate) which facilitates the validation of a devices state by generating a compliance report based on specific validation criteria. This criteria centres around the differing features enabled on a device, see the [nornir-validate documentation](https://nornir-validate.readthedocs.io/en/latest/index.html) for more in-depth details and a full list of [supported validations](https://nornir-validate.readthedocs.io/en/latest/validations.html).

## Installation and Variables

Clone the repository and install the required python packages, the easiest way to do this is with [uv](https://docs.astral.sh/uv/) as it automatically creates and activates the virtual environment.

```python
git clone https://github.com/sjhloco/nornir_ppcheck.git
cd nornir_ppcheck/

uv sync
```

If you are using [pip](https://pypi.org/project/pip/) first create and activate the virtual environment before installing the packages.

```python
python -m venv .venv
.\.venv\Scripts\Activate
pip install -r requirements.txt
```

The below table lists the changeable elements of the script, if an element is set via multiple methods the order of preference is ***runtime flag >> environment variable >> script variable***.

| Element | Runtime flag | Environment variable | Script variable | Default | Information |
| ------- | ------------ | -------------------- | --------------- | ------- | ----------- |
| Username | -u/--username | DEVICE_USER | default_user | admin | Username for all devices |
| Password | n/a | DEVICE_PWORD | n/a | n/a | Password for all devices, if the env var is not set prompts for a password at runtime |
| Base directory | n/a | BASE_DIRECTORY | n/a | current working directory | Location where the change folder can be found |
| Command input file | n/a | INPUT_CMD_FILE | n/a | input_cmds.yml | Looks in the change folder for a command input file with this name |
| Validate index file | n/a | INPUT_INDEX_FILE | n/a | input_index.yml | Looks in the change folder for a index file with this name |
| Nornir Inventory | n/a | n/a | inventory | BASE_DIRECTORY/inventory | Location of nornir inventory |

## Inventory - What devices to run the script against

The first thing to do is refine the filters to limit the inventory to only the required hosts, the filters are based on pre-defined groups (*inventory/group.yml*) and host variables (*inventory/hosts.yml*). Use `-s` (***show***) or `-sd` (***show detail***) and the appropriate filters to display what hosts the filtered inventory holds. ***You are not running any actions against devices at this stage, just the filtering the inventory***.

| Filter | Description | Filter example |
| ------ | ----------- | ------- |
| `-n` | Match ***hostname*** containing this string (OR logic upto 10 hosts encased in "" separated by a space) | -n "DC1-N9K LON-ASR-WAN02" |
| `-g` | Match a ***group*** or combination of groups *(ios, iosxe, nxos, wlc, asa, paloalto, viptela)* | -g ios iosxe |
| `-l` | Match a ***physical location*** or combination of them *(DC1, DC2, LON, MAN, CMP*) | -l DC1 DC2 |
| `-ll` | Match a ***logical location*** or combination of them *(WAN Edge, Core, Access, Services)* | -ll Core "WAN Edge" |
| `-t` | Match a ***device type*** or combination of them *(router, switch, firewall, controller)* | -t switch controller |
| `-v` | Match any ***version*** that contains this string | -v 17.6.3a |

```bash
uv run main.py -s                           # Lists all hosts in the inventory, the host (friendly name) and hostname (or IP)
uv run main.py -n DC1-N9K-BGW -sd           # Displays detailed host information (host_vars)
uv run main.py -g nxos iosxe -s             # See all NXOS or IOSXE hosts
uv run main.py -l LON -ll Core Access -s    # All Core and Access devices at LON site
uv run main.py -g nxos -n BGW -s            # All NXOS with BGW in the host name
```

Although you can in theory run the script against all devices in one go, when planning your filters it’s better to split it up and run the script multiple times against different groups of devices as the terminal can become too noisy with all the printed outputs.

## Credentials

The *username* and *password* can be passed in at run time (`-u` flag, password dynamically prompted) or set in environment variables (`export DEVICE_USER="me"`, `export DEVICE_PWORD="blah"`). It is also possible to hardcode the username variable (`default_user`) within the script (*main.py*), the default username is *admin*.

## Running Pre/Post-checks

Pre and post-checks are similar in the tasks they perform with both relying on an input file of commands.

### Input file - What commands are to be run

By default the command input file is expected to be called ***input_cmds.yml*** and saved within the *change folder* (defined at runtime). This file is structured around 3 optional parent dictionaries (are merge at runtime), you must have at least 1 of these defined.

- **hosts:** Specify commands to be run on a per-host basis (will also run commands in matching group and all)
- **groups:** Specify commands to be run on all members of this group (will also run cmds in all)
- **all:** Specify commands to be run on all hosts

Within these parent dictionaries you can have any or all the following child dictionaries:
- **run_cfg:** Set to true to save the running config to file
- **cmd_print:** List of commands that the output from will be printed to screen
- **cmd_vital:** List of commands that the output from will be saved to file to be compared at the end of a change
- **cmd_detail:** List of commands that the output from will be saved to file in case encounter problems after the change

Below is an example to save the *running config* to file and run a few commands on one device (*HME-C3560-SWI01*), a few commands on all *NXOS* devices and the final set of commands on all devices. Obviously this will only apply to hosts that were matched by the inventory filter used at runtime.

```yaml
hosts:
  HME-C3560-SWI01:
    run_cfg: True
    cmd_print:
      - show cdp neighbors
      - show ip int brief
    cmd_vital:
      - show run interface GigabitEthernet0/2
groups:
  nxos:
    cmd_print:
      - show interface status up
    cmd_vital:
      - show interface status
all:
  cmd_vital:
    - show ip arp summary
  cmd_detail:
    - show ip arp
```

### Pre-checks

Run the script with `-pre change_folder_name`, it will loop through all the matched devices from the inventory and do the following:
- Print the ***cmd_print*** commands to screen
- Save the ***cmd_vital***, ***cmd_detail*** and ***run_cfg*** command outputs in separate files within a newly created *output* folder in the specified change directory.

```bash
uv run main.py -l Netlab -ll Core Access -g iosxe -s
uv run main.py -l Netlab -ll Core Access -g iosxe -pre "CHxx - Test change"
```

### Post-checks

Running the post-check is the same process except the `-pos` flag is used, this will do the following:
- Print the ***cmd_print*** commands to screen
- Save the ***cmd_vital*** and ***run_cfg*** command outputs in separate files within the *output* folder
- Compare the two latest vital files for each device and save the results as a HTML file
- Compare the two latest running config files for each device and save the results as a HTML file

```bash
uv run main.py -l Netlab -ll Core Access -g iosxe -pos "CHxx - Test change"
```

The *.html* diff files can be view in a browser, green is added, yellow changed and red deleted. Like any diff the formatting isn’t 100% perfect but gives you a good idea of what has changed. If for some reason you run `pre` more than once rename or remove the unneeded files from the *output* folder before running the post-checks as it will only compare the new output files against the next oldest files.

<img width="1335" height="765" alt="Image" src="https://github.com/user-attachments/assets/82c45e1e-6eea-4e56-b5bf-64495d22932a" />

### Extra Information

The `pre` and `pos` flags just wrappers to combine multiple actions into the one command, any of these actions can be performed individually using the relevant runtime flags from the table below.

| runtime | Description |
| ------- | ----------- |
| `-prt` | ***Prints*** command outputs (*cmd_print*), requires name of the change directory or full path to the file |
| `-vtl` | ***Saves vital*** command outputs (*cmd_vital*) to file, requires name of the change directory |
| `-dtl` | ***Saves detail*** command outputs (*cmd_detail*) to file, requires name of the change directory |
| `-com` | ***Compares*** 2 files to create a HTML file, requires name of the change directory and two file names (that are located in the change directory) |

## Running Nornir-validate

Nornir-validate produces a compliance report by comparing the devices actual state against a validation file of YAML-based specifications (desired state). These validation files can be manually ([example validation files](https://github.com/sjhloco/nornir-validate/tree/main/example_validation_files)) or automatically generated, they follow the same format as pre/post-checks in the in the sense of *hosts*, *groups* and *all* dictionaries, within each you can define all features or a subset of features.

### Generate Validation Files

Automatically generated validation files are built based off an index of [feature.sub-feature](https://nornir-validate.readthedocs.io/en/latest/validations.html) ([example index files](https://github.com/sjhloco/nornir-validate/tree/main/src/nornir_validate/index_files)), there are few different ways in which these validation files can be generated:

- ***No index file -*** Run the script specifying a change folder which has an no index file: Creates validation filea based off all features enabled on the device and saves them in the *val_files* folder (created if doesn't exist) of the change folder (1 file for each device).\
`uv run main.py -n R1 -gvf "Chxxx - Test val"`

- ***Default index file -*** Run the script specifying a change folder which has an index file (named *input_index.yml*): Creates validation files based off the indexes in the file (if the feature is enabled) and saves them in the *val_files* folder.\
`uv run main.py -n R1 -gvf "Chxxx - Test val1"`

- ***Path to index_file -*** Run the script with an explicitly defined index file (full path to the index file): Creates validation files based off the indexes in the file (if the feature is enabled) and saves them in the *val_files* folder in the same location where the index file is.\
`uv run main.py -n R1 -gvf "Chxxx - Test val2/custom_index.yml"`

### Compliance Report

The compliance report is generated based off the validation files, there are two ways to run the script:

- ***Path to change folder:*** Looks for all *.yml* files in */val_files* and merges them before creating the compliance report and saving it to *change_dir/output*. The report status is printed to screen (complies *True/False*) along with the full path to the report, if it fails the full compliance report is also printed.\
`uv run ./main.py -val "Chxxx - Test val3"`

- ***Path to validation file:*** Full path to a validation file (can contain validations for many devices), as no directory is specified it doesn't save the compliance report and instead prints the full report (pass or fail) to screen./
`uv run ./main.py -val "all_devices_val_file.yml"`

## Example outputs

- **Filters:** Filter down to specific hosts or collection of hosts based on *hostname, group, logical location, etc*
  <img width="1043" height="128" alt="Image" src="https://github.com/user-attachments/assets/a60b6064-3613-4955-9f33-f45e5cce9bc6" />

- **Print commands to screen (prt):** Runs a list of commands and prints the output to screen
  <img width="1248" height="181" alt="Image" src="https://github.com/user-attachments/assets/15c8e6ba-2037-40a7-a60a-dfa2cd8ca2a0" />

- **pre-test (pre):** Runs *print*, *save vital* and *save_detail* (and saves *running config* if enabled)
  <img width="1248" height="181" alt="Image" src="https://github.com/user-attachments/assets/0c6b952e-76e3-4d7d-8780-1782d98adba2" />
  
- **post-test (pos):** Runs *print*, *save vital* and *compare* against last two vital files (and *running config* if enabled)
  <img width="1245" height="435" alt="Image" src="https://github.com/user-attachments/assets/85a89931-2d8c-4ed4-887f-427424a29b6d" />

- **Generate validation files (gvf):** Generates a validation file for all enabled features
  <img width="1245" height="435" alt="Image" src="https://github.com/user-attachments/assets/72815e91-45f9-4121-88e0-87b17af2b857" />

- **Compliance report (val):** Creates a compliance report based off validation files
  <img width="1245" height="795" alt="Image" src="https://github.com/user-attachments/assets/fc4a0804-892c-463d-8828-cab4d6c520ab" />

## Test suite

The script uses the following tools for testing:

- [Ruff Formatter](https://docs.astral.sh/ruff/formatter/) is a code formatter for Python that focuses on speed and correctness, similar to black but with a different design philosophy
- [Ruff Linter](https://docs.astral.sh/ruff/linter/) is an extremely fast Python linter designed as a drop-in replacement for Flake8, isort, pydocstyle, pyupgrade, autoflake, and more
- [MyPy](https://mypy-lang.org) performs static type checking
- [PyTest](https://docs.pytest.org/en/stable/) unit-tests validates core nornir-validate functions and all of the feature templates

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest -v
```

Pytest unit testing is split into different classes to allow for the different script elements to be tested  if need be.

```bash
uv run pytest test/test_main.py::TestInputValidateFileValidation -v
uv run pytest test/test_main.py::TestInputValidateMergeValFiles -v
uv run pytest test/test_main.py::TestInputValidateArgumentProcessing -v
uv run pytest test/test_main.py::TestInputValidateNoncompareArg -v
uv run pytest test/test_main.py::TestInputValidateValArg -v
uv run pytest test/test_main.py::TestInputValidateCredentials -v
uv run pytest test/test_main.py::TestNornirCommandsOrganization -v
uv run pytest test/test_main.py::TestNornirCommandsDiffCreation -v
uv run pytest test/test_main.py::TestNornirCommandsRunCommands -v
uv run pytest test/test_main.py::TestNornirCommandsSaveCommands -v
uv run pytest test/test_main.py::TestIntegration -v
```
