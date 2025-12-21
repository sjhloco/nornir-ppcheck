# Nornir Pre/Post Checks

The idea behind this project is to gather the facts (command outputs) about the network state before and after a change and compare the results. There are 3 different command outputs that we are interested in for this purpose:

- **Print:** Outputs printed to screen so we can eyeball the network state before the change
- **vital:** Outputs to compare after the change, will likely be some overlap with the print commands
- **detail:** Outputs only really needed if we have issues after a change (for example full ARP or MAC table)

*Nornir* is used to gather the command output with the scope of devices being based on a static inventory and pre-built filters. The inventory is defined in its own module (*nornir_inv.py*) with the idea being that it will make it easier to swap out for a dynamic inventory plugin if need be.

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
| --------| ------------ | -------------------- | --------------- | ------- | ------------|
| Username | -u/--username | DEVICE_USER | default_user | admin | Username for all devices |
| Password | n/a | DEVICE_PWORD | n/a | n/a | Password for all devices, if the env var is not set prompts for a password at runtime |
| Base directory | n/a | BASE_DIRECTORY | n/a | current working directory | Location of the change folder |
| Command input file | n/a | INPUT_CMD_FILE | n/a | input_cmds.yml | Looks in change folder for a file of this name |
| Nornir Inventory | n/a | n/a | inventory | BASE_DIRECTORY/inventory | Location of nornir inventory |

## Inventory - What devices to run the script against

The first thing to do is refine the filters to limit the inventory to only the required hosts, the filters are based on pre-defined groups (*inventory/group.yml*) and host variables (*inventory/hosts.yml*). Use `-s` (***show***) or `-sd` (***show detail***) and the appropriate filters to display what hosts the filtered inventory holds. ==***You are not running any actions against devices at this stage, just the filtering the inventory***==.

| Filter | Description | Filter example |
| ------ | ----------- | ------- |
| `-n` | Match ***hostname*** containing this string (OR logic upto 10 hosts encased in "" separated by a space) | -n "DC1-N9K LON-ASR-WAN02" |
| `-g` | Match a ***group*** or combination of groups *(ios, iosxe, nxos, wlc, asa, paloalto, viptela)* | -g ios iosxe  |
| `-l` | Match a ***physical location*** or combination of them *(DC1, DC2, LON, MAN, CMP*) | -l DC1 DC2 |
| `-ll` | Match a ***logical location*** or combination of them *(WAN Edge, Core, Access, Services)* | -ll Core "WAN Edge" |
| `-t` | Match a ***device type*** or combination of them *(router, switch, firewall, controller)* | -t dc_switch controller |
| `-v` | Match any ***version*** that contains this string | -v 17.6.3a |

```bash
uv run main.py -s                           # Lists all hosts in the inventory, the host (friendly name) and hostname (IP)
uv run main.py -n DC1-N9K-BGW -sd           # Displays detailed host information (host_vars)
uv run main.py -g nxos iosxe -s             # See all NXOS or IOSXE hosts
uv run main.py -l LON -ll Core Access -s    # All Core and Access devices at LON site
uv run main.py -g nxos -n BGW -s            # All NXOS with BGW in the host name
```

Although you can in theory run the script against all devices in one go, when planning your filters it’s better to split it up and run the script multiple times against different groups of devices as the terminal can become too noisy with all the printed outputs.

## Input file - What commands are to be run

The command input file must be called ***input_cmds.yml*** and saved in the *change folder* (defined at runtime). This file is structured around 3 optional parent dictionaries (are merge at runtime), you must have at least 1 of these defined.

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

## Running the script

The *username* and *password* can be passed in at run time (`-u` flag, password dynamically prompted) or set in environment variables (`export DEVICE_USER="me"`, `export DEVICE_PWORD="blah"`). It is also possible to hardcode the username variable (`default_user`), the default username is *admin*.

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
- Save the ***cmd_vital***, ***cmd_detail*** and ***run_cfg*** command outputs in separate files within the *output* folder
- Compare the two latest vital files for each device and save the results as a HTML file
- Compare the two latest running config files for each device and save the results as a HTML file

```bash
uv run main.py -l Netlab -ll Core Access -g iosxe -pos "CHxx - Test change"
```

The *.html* diff files can be view in a browser, green is added, yellow changed and red deleted. Like any diff the formatting isn’t 100% perfect but gives you a good idea of what has changed. If for some reason you run `pre` more than once rename or remove the unneeded files from the output folder before running the post-checks as it will only compare the new output filess against the next oldest files.

IMAGE OF DIFF

### Extra Information

The `pre` and `pos` flags just combine multiple actions into the one command, any of these actions can be performed individually using the relevant runtime flags from the table below.

| runtime          | Description |
| -------------- | ----------- |
| `-u` | Overrides the ***Network device username*** set by env vars and/or hardcoded variables |
| `-prt` | ***Prints*** command outputs (*cmd_print*), requires name of the change directory or files full path |
| `-vtl` | ***Saves vital*** command outputs (*cmd_vital*) to file, requires name of the change directory |
| `-dtl` | ***Saves detail*** command outputs (*cmd_detail*) to file, requires name of the change directory |
| `-com` | ***Compares*** 2 files to create a HTML file, requires name of the change directory and two file names (that are located in the change directory) |
| `-pre` | Runs *print*, *save vital* and *save_detail* |
| `-pos` | Runs *print*, *save vital* and *compare* |

## Example outputs

- **Filters:** Filter down to specific hosts or collection of hosts based on *hostname, group, logical location, etc*
  
  IMAGE of filter

- **Print commands to screen (prt):** Runs a list of commands and prints the output to screen

  Image of prt

- **pre-test(pre):** Runs *print*, *save vital* and *save_detail* (and saves *running config* if enabled)

  Image of pre
  
- **post-test(pos):** Runs *print*, *save vital* and *compare* against last two vital files (and *running config* if enabled)

  Image of pos

<!--
## Unit testing

Pytest unit testing is split into two classes to test inventory settings validation and Nornir interactions

```python
pytest test/test_main.py::TestInputValidate -v
pytest test/test_main.py::TestNornirCommands -v
pytest test/test_main.py -v
```

 | `-val` | Creates a compliance report and saves to file, requires name of the change directory

## Input files

There are two types of input files that can be used with the script, one to print or save command output (*input_cmd.yml*) and the other for validation (*input_val.yml*).

 ### Input validate *(input_val.yml)*

If there are any conflicts between the objects *groups* takes precedence over *all* and *hosts* takes precedence over *groups*. This example validates port-channels on all devices, ACLs on all IOS devices and OSPF neighbors just on HME-SWI-VSS01.

```yaml
hosts:
  HME-SWI-VSS01:
    ospf:
      nbrs: [192.168.255.1]
groups:
  ios:
    acl:
      - name: TEST_SSH_ACCESS
        ace:
          - { remark: MGMT Access - VLAN10 }
          - { permit: 10.17.10.0/24 }
          - { remark: Citrix Access }
          - { permit: 10.10.10.10/32 }
          - { deny: any }
all:
  po:
    - name: Po3
      mode: LACP
      members: [Gi0/15, Gi0/16]

**validate:** Creates a compliance report that is saved in the output directory. If compliance fails the report will also be be printed to screen

``` -->
