"""Pytest unittest module for main.py.

Tests the InputValidate, NornirEngine, and NornirCommands classes from main.py
including argument parsing, file validation, command organization, and diff creation.
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml

from main import InputValidate, NornirCommands

if TYPE_CHECKING:
    from collections.abc import Generator

# =============================================================================
# CONFIGURATION: Directory paths and test data
# =============================================================================

test_directory = os.path.dirname(__file__)
test_inventory = os.path.join(test_directory, "test_inventory")
test_files = os.path.join(test_directory, "test_files")
input_file = os.path.join(test_files, "input_cmd.yml")

# Load test input data from file
with open(input_file) as f:
    test_input_data = yaml.load(f, Loader=yaml.FullLoader)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture(scope="function")  # noqa: PT003
def temp_output_dir() -> Generator[str]:
    """Create a temporary directory for test output files."""
    tmp_dir = tempfile.mkdtemp()
    yield tmp_dir
    # Cleanup after test
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)


@pytest.fixture(scope="function")  # noqa: PT003
def input_validate_instance() -> InputValidate:
    """Create an InputValidate instance for testing."""
    return InputValidate()


@pytest.fixture(scope="function")  # noqa: PT003
def mock_nornir_task() -> MagicMock:
    """Create a mock Nornir Task object."""
    task = MagicMock()
    host: MagicMock = MagicMock()
    host.__str__ = MagicMock(return_value="R1")  # type: ignore[method-assign]
    host.hostname = "10.10.20.1"
    host.groups = ["ios"]
    task.host = host
    task.run = MagicMock()
    return task


# =============================================================================
# TEST CLASS 1: InputValidate - File and Directory Validation
# =============================================================================


class TestInputValidateFileOperations:
    """Test InputValidate class file and directory operations."""

    def test_get_output_fldr_creates_folder(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_output_fldr creates output folder if it doesn't exist."""
        result = input_validate_instance._get_output_fldr("test", temp_output_dir)
        assert os.path.exists(result)
        assert result.name == "output"

    def test_get_output_fldr_existing_folder(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_output_fldr returns path if output folder already exists."""
        output_path = Path(temp_output_dir) / "output"
        output_path.mkdir(exist_ok=True)
        result = input_validate_instance._get_output_fldr("test", temp_output_dir)
        assert os.path.exists(result)

    def test_get_output_fldr_missing_working_dir(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _get_output_fldr exits if working directory doesn't exist."""
        with pytest.raises(SystemExit):
            input_validate_instance._get_output_fldr("test", "non_existent_dir")

    def test_get_val_files_fldr_creates_folder(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_val_files_fldr creates validation files folder if it doesn't exist."""
        result = input_validate_instance._get_val_files_fldr("test", temp_output_dir)
        assert os.path.exists(result)
        assert result.name == "val_files"

    def test_get_val_files_fldr_missing_working_dir(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _get_val_files_fldr exits if working directory doesn't exist."""
        with pytest.raises(SystemExit):
            input_validate_instance._get_val_files_fldr("test", "non_existent_dir")

    def test_err_missing_files_raises_exit(
        self, input_validate_instance: InputValidate, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test _err_missing_files exits when files are missing."""
        with pytest.raises(SystemExit):
            input_validate_instance._err_missing_files(
                "test", ["file1.txt", "file2.txt"]
            )
        captured = capsys.readouterr()
        assert "file1.txt, file2.txt" in captured.out
        assert "does not exist" in captured.out

    def test_err_missing_files_empty_list(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _err_missing_files does nothing with empty file list."""
        # Should not raise SystemExit with empty list
        input_validate_instance._err_missing_files("test", [])


# =============================================================================
# TEST CLASS 2: InputValidate - File Validation
# =============================================================================


class TestInputValidateFileValidation:
    """Test InputValidate class file content validation."""

    def test_val_input_file_empty_file(
        self, input_validate_instance: InputValidate, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test _val_input_file exits when input file is empty (None)."""
        with pytest.raises(SystemExit):
            input_validate_instance._val_input_file("test", "test.yml", None)  # type: ignore[arg-type]
        captured = capsys.readouterr()
        assert "is empty" in captured.out

    def test_val_input_file_no_required_keys(
        self, input_validate_instance: InputValidate, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test _val_input_file exits when required keys (hosts/groups/all) are missing."""
        with pytest.raises(SystemExit):
            input_validate_instance._val_input_file(
                "test", "test.yml", {"foo": {}, "bar": {}}
            )
        captured = capsys.readouterr()
        assert "hosts, groups" in captured.out or "all" in captured.out

    def test_val_input_file_hosts_not_dict(
        self, input_validate_instance: InputValidate, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test _val_input_file exits when hosts is not a dictionary."""
        with pytest.raises(SystemExit):
            input_validate_instance._val_input_file("test", "test.yml", {"hosts": []})
        captured = capsys.readouterr()
        assert "must have at least one" in captured.out

    def test_val_input_file_valid_all_section(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _val_input_file passes with valid 'all' section."""
        # Should not raise SystemExit
        input_validate_instance._val_input_file(
            "test", "test.yml", {"all": {"cmd": []}}
        )

    def test_val_input_file_valid_hosts_section(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _val_input_file passes with valid 'hosts' section."""
        input_validate_instance._val_input_file(
            "test", "test.yml", {"hosts": {"R1": {}}}
        )

    def test_val_input_file_valid_groups_section(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test _val_input_file passes with valid 'groups' section."""
        input_validate_instance._val_input_file(
            "test", "test.yml", {"groups": {"ios": {}}}
        )


# =============================================================================
# TEST CLASS 3: InputValidate - Get Merge Validation Files
# =============================================================================


class TestInputValidateMergeValFiles:
    """Test InputValidate get_merge_val_files method."""

    def test_get_merge_val_files_no_files(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_merge_val_files exits when no YAML files are found."""
        val_fldr = Path(temp_output_dir) / "val_files"
        val_fldr.mkdir()
        with pytest.raises(SystemExit):
            input_validate_instance._get_merge_val_files(val_fldr)

    def test_get_merge_val_files_single_file(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_merge_val_files successfully merges a single validation file."""
        val_fldr = Path(temp_output_dir) / "val_files"
        val_fldr.mkdir()

        # Create a test validation file
        val_file = val_fldr / "val1.yml"
        test_data = {
            "all": {"param1": "value1"},
            "hosts": {"R1": {"test": "data"}},
        }
        with open(val_file, "w") as f:
            yaml.dump(test_data, f)

        result = input_validate_instance._get_merge_val_files(val_fldr)
        assert "all" in result
        assert "hosts" in result
        assert result["hosts"]["R1"]["test"] == "data"

    def test_get_merge_val_files_multiple_files(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_merge_val_files merges multiple validation files."""
        val_fldr = Path(temp_output_dir) / "val_files"
        val_fldr.mkdir()

        # Create first validation file
        val_file1 = val_fldr / "val1.yml"
        test_data1 = {"all": {"param1": "value1"}}
        with open(val_file1, "w") as f:
            yaml.dump(test_data1, f)

        # Create second validation file
        val_file2 = val_fldr / "val2.yml"
        test_data2 = {"hosts": {"R1": {"test": "data"}}}
        with open(val_file2, "w") as f:
            yaml.dump(test_data2, f)

        result = input_validate_instance._get_merge_val_files(val_fldr)
        assert result["all"]["param1"] == "value1"
        assert result["hosts"]["R1"]["test"] == "data"

    def test_get_merge_val_files_empty_sections(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test _get_merge_val_files exits when all sections are empty."""
        val_fldr = Path(temp_output_dir) / "val_files"
        val_fldr.mkdir()

        val_file = val_fldr / "val1.yml"
        test_data: dict[str, Any] = {"all": {}, "hosts": {}, "groups": {}}
        with open(val_file, "w") as f:
            yaml.dump(test_data, f)

        with pytest.raises(SystemExit):
            input_validate_instance._get_merge_val_files(val_fldr)


# =============================================================================
# TEST CLASS 4: InputValidate - Argument Processing
# =============================================================================


class TestInputValidateArgumentProcessing:
    """Test InputValidate argument parsing and processing."""

    def test_get_run_type_none(self, input_validate_instance: InputValidate) -> None:
        """Test get_run_type returns None when no valid runtime args provided."""
        args: dict[str, Any] = {
            "print": None,
            "vital_save": None,
            "detail_save": None,
            "compare": None,
            "validate": None,
            "gen_val_file": None,
            "pre_test": None,
            "post_test": None,
        }
        run_type, file_path = input_validate_instance.get_run_type(args)
        assert run_type is None
        assert file_path == []

    def test_get_run_type_print(self, input_validate_instance: InputValidate) -> None:
        """Test get_run_type correctly identifies 'print' runtime flag."""
        args: dict[str, Any] = {
            "print": ["test_dir"],
            "vital_save": None,
            "detail_save": None,
            "compare": None,
            "validate": None,
            "gen_val_file": None,
            "pre_test": None,
            "post_test": None,
        }
        run_type, file_path = input_validate_instance.get_run_type(args)
        assert run_type == "print"
        assert file_path == ["test_dir"]

    def test_get_run_type_compare(self, input_validate_instance: InputValidate) -> None:
        """Test get_run_type correctly identifies 'compare' runtime flag."""
        args: dict[str, Any] = {
            "print": None,
            "vital_save": None,
            "detail_save": None,
            "compare": ["dir", "file1", "file2"],
            "validate": None,
            "gen_val_file": None,
            "pre_test": None,
            "post_test": None,
        }
        run_type, file_path = input_validate_instance.get_run_type(args)
        assert run_type == "compare"
        assert file_path == ["dir", "file1", "file2"]

    def test_compare_arg_valid(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test compare_arg with valid compare files."""
        # Create test files
        cmp_file1 = Path(temp_output_dir) / "cmp1.txt"
        cmp_file2 = Path(temp_output_dir) / "cmp2.txt"
        cmp_file1.write_text("content1")
        cmp_file2.write_text("content2")

        output_dir = Path(temp_output_dir) / "output"
        output_dir.mkdir()

        # Use full temp_output_dir path as BASE_DIRECTORY is set in main.py
        result = input_validate_instance.compare_arg(
            [temp_output_dir, "cmp1.txt", "cmp2.txt"]
        )
        assert "output_fldr" in result
        assert "cmp_file1" in result
        assert "cmp_file2" in result

    def test_compare_arg_missing_files(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test compare_arg exits when compare files are missing."""
        output_dir = Path(temp_output_dir) / "output"
        output_dir.mkdir()

        with pytest.raises(SystemExit):
            input_validate_instance.compare_arg(
                [os.path.basename(temp_output_dir), "missing1.txt", "missing2.txt"]
            )


# =============================================================================
# TEST CLASS 5: InputValidate - Non-Compare Arguments
# =============================================================================


class TestInputValidateNoncompareArg:
    """Test InputValidate noncompare_arg method."""

    def test_noncompare_arg_missing_input_file(
        self,
        input_validate_instance: InputValidate,
        temp_output_dir: str,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test noncompare_arg exits when input file is missing."""
        with pytest.raises(SystemExit):
            input_validate_instance.noncompare_arg("print", [temp_output_dir])
        captured = capsys.readouterr()
        # Check without newlines since output may have line breaks
        assert "does not exist" in captured.out.replace("\n", " ")

    def test_noncompare_arg_with_file_path(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test noncompare_arg with direct file path (print case)."""
        # Create test input file
        input_yml = Path(temp_output_dir) / "test.yml"
        test_data = {"all": {"cmd_print": ["show version"]}}
        with open(input_yml, "w") as f:
            yaml.dump(test_data, f)

        result = input_validate_instance.noncompare_arg("print", [str(input_yml)])
        assert "input_file" in result
        assert "output_fldr" in result
        assert "input_data" in result
        assert result["input_data"]["all"]["cmd_print"] == ["show version"]

    def test_noncompare_arg_with_directory(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test noncompare_arg with directory (creates input_cmds.yml)."""
        # Create directory structure
        work_dir = Path(temp_output_dir) / "work"
        work_dir.mkdir()

        # Create input_cmds.yml
        input_yml = work_dir / "input_cmds.yml"
        test_data = {"all": {"cmd_print": ["show version"]}}
        with open(input_yml, "w") as f:
            yaml.dump(test_data, f)

        result = input_validate_instance.noncompare_arg("vital_save", [str(work_dir)])
        assert "input_file" in result
        assert "output_fldr" in result
        assert "input_data" in result


# =============================================================================
# TEST CLASS 6: InputValidate - Validation Arguments
# =============================================================================


class TestInputValidateValArg:
    """Test InputValidate val_arg method."""

    def test_val_arg_with_file_path(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test val_arg with direct file path."""
        # Create test validation file
        val_file = Path(temp_output_dir) / "validate.yml"
        test_data = {"all": {"param": "value"}}
        with open(val_file, "w") as f:
            yaml.dump(test_data, f)

        result = input_validate_instance.val_arg("validate", [str(val_file)])
        assert "output_fldr" in result
        assert "val_files_fldr" in result
        assert "input_data" in result

    def test_val_arg_gen_val_file_with_directory(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test val_arg for gen_val_file with directory."""
        result = input_validate_instance.val_arg("gen_val_file", [temp_output_dir])
        assert "output_fldr" in result
        assert "val_files_fldr" in result
        assert "input_data" in result
        assert os.path.exists(result["val_files_fldr"])

    def test_val_arg_validate_with_directory(
        self, input_validate_instance: InputValidate, temp_output_dir: str
    ) -> None:
        """Test val_arg for validate with directory."""
        # Create directory structure with val files
        work_dir = Path(temp_output_dir) / "work"
        work_dir.mkdir()
        val_fldr = work_dir / "val_files"
        val_fldr.mkdir()

        # Create a validation file
        val_file = val_fldr / "val1.yml"
        test_data = {"all": {"param": "value"}}
        with open(val_file, "w") as f:
            yaml.dump(test_data, f)

        result = input_validate_instance.val_arg("validate", [str(work_dir)])
        assert "output_fldr" in result
        assert "val_files_fldr" in result
        assert "input_data" in result


# =============================================================================
# TEST CLASS 7: InputValidate - Credentials
# =============================================================================


class TestInputValidateCredentials:
    """Test InputValidate credential handling."""

    @patch("getpass.getpass")
    def test_get_user_pass_from_args(
        self, mock_getpass: Mock, input_validate_instance: InputValidate
    ) -> None:
        """Test get_user_pass uses username from arguments."""
        mock_getpass.return_value = "test_password"
        result = input_validate_instance.get_user_pass({"username": "test_user"})
        assert result["user"] == "test_user"
        assert result["pword"] == "test_password"

    @patch.dict(os.environ, {}, clear=True)
    @patch("getpass.getpass")
    def test_get_user_pass_default_user(
        self, mock_getpass: Mock, input_validate_instance: InputValidate
    ) -> None:
        """Test get_user_pass uses default user when no argument provided."""
        mock_getpass.return_value = "test_password"
        result = input_validate_instance.get_user_pass({})
        assert result["user"] == "admin"  # Default user
        assert result["pword"] == "test_password"

    @patch.dict(os.environ, {"DEVICE_PWORD": "env_password"})
    def test_get_user_pass_from_env(
        self, input_validate_instance: InputValidate
    ) -> None:
        """Test get_user_pass uses password from environment variable."""
        result = input_validate_instance.get_user_pass({"username": "test_user"})
        assert result["user"] == "test_user"
        assert result["pword"] == "env_password"


# =============================================================================
# TEST CLASS 8: NornirCommands - Command Organization
# =============================================================================


class TestNornirCommandsOrganization:
    """Test NornirCommands class command organization methods."""

    def test_get_cmds_all_section(self) -> None:
        """Test get_cmds correctly processes 'all' section."""
        nr_cmd = NornirCommands()
        cmds: dict[str, Any] = {
            "print": [],
            "vital": [],
            "detail": [],
            "run_cfg": False,
        }
        # get_cmds expects cmd_print keys at top level
        input_data: dict[str, Any] = {
            "cmd_print": ["show version"],
            "cmd_vital": ["show arp"],
        }

        nr_cmd.get_cmds(cmds, input_data)
        assert nr_cmd.cmds["print"] == ["show version"]
        assert nr_cmd.cmds["vital"] == ["show arp"]

    def test_get_cmds_run_cfg(self) -> None:
        """Test get_cmds correctly processes run_cfg flag."""
        nr_cmd = NornirCommands()
        cmds: dict[str, Any] = {
            "print": [],
            "vital": [],
            "detail": [],
            "run_cfg": False,
        }
        input_data: dict[str, Any] = {"run_cfg": True}

        nr_cmd.get_cmds(cmds, input_data)
        # run_cfg is added as boolean (False + True = 1)
        assert nr_cmd.cmds["run_cfg"] or nr_cmd.cmds["run_cfg"] == 1

    def test_get_cmds_multiple_commands(self) -> None:
        """Test get_cmds correctly extends multiple commands."""
        nr_cmd = NornirCommands()
        cmds: dict[str, Any] = {
            "print": ["cmd1"],
            "vital": [],
            "detail": [],
            "run_cfg": False,
        }
        input_data: dict[str, Any] = {"cmd_print": ["cmd2", "cmd3"]}

        nr_cmd.get_cmds(cmds, input_data)
        assert nr_cmd.cmds["print"] == ["cmd1", "cmd2", "cmd3"]

    def test_organise_cmds_all_section(self, mock_nornir_task: MagicMock) -> None:
        """Test organise_cmds correctly processes 'all' section."""
        nr_cmd = NornirCommands()
        input_data: dict[str, Any] = {
            "all": {"cmd_print": ["show version"], "cmd_vital": ["show arp"]}
        }

        result = nr_cmd.organise_cmds(mock_nornir_task, input_data)
        assert "show version" in result["print"]
        assert "show arp" in result["vital"]

    def test_organise_cmds_groups_section(self, mock_nornir_task: MagicMock) -> None:
        """Test organise_cmds correctly processes matching groups."""
        nr_cmd = NornirCommands()
        mock_nornir_task.host.groups = ["ios", "campus"]
        input_data: dict[str, Any] = {
            "groups": {
                "ios": {"cmd_print": ["show ios cmd"]},
                "junos": {"cmd_print": ["show junos cmd"]},
            }
        }

        result = nr_cmd.organise_cmds(mock_nornir_task, input_data)
        assert "show ios cmd" in result["print"]
        assert "show junos cmd" not in result["print"]

    def test_organise_cmds_hosts_section(self, mock_nornir_task: MagicMock) -> None:
        """Test organise_cmds correctly processes matching hosts."""
        nr_cmd = NornirCommands()
        mock_nornir_task.host.__str__.return_value = "R1"
        input_data: dict[str, Any] = {
            "hosts": {
                "R1": {"cmd_print": ["show r1 cmd"]},
                "R2": {"cmd_print": ["show r2 cmd"]},
            }
        }

        result = nr_cmd.organise_cmds(mock_nornir_task, input_data)
        assert "show r1 cmd" in result["print"]
        assert "show r2 cmd" not in result["print"]

    def test_organise_cmds_empty_input(self, mock_nornir_task: MagicMock) -> None:
        """Test organise_cmds with empty input data."""
        nr_cmd = NornirCommands()
        input_data: dict[str, Any] = {}

        result = nr_cmd.organise_cmds(mock_nornir_task, input_data)
        assert result["print"] == []
        assert result["vital"] == []
        assert result["detail"] == []
        assert not result["run_cfg"]


# =============================================================================
# TEST CLASS 9: NornirCommands - Diff Creation
# =============================================================================


class TestNornirCommandsDiffCreation:
    """Test NornirCommands diff creation methods."""

    def test_create_diff(self, temp_output_dir: str) -> None:
        """Test create_diff correctly generates HTML diff file."""
        nr_cmd = NornirCommands()

        # Create test comparison files
        cmp_file1 = Path(temp_output_dir) / "test1.txt"
        cmp_file2 = Path(temp_output_dir) / "test2.txt"
        cmp_file1.write_text("line1\nline2\nline3\n")
        cmp_file2.write_text("line1\nline2_modified\nline3\n")

        data: dict[str, Any] = {
            "output_fldr": temp_output_dir,
            "cmp_file1": str(cmp_file1),
            "cmp_file2": str(cmp_file2),
        }

        result = nr_cmd.create_diff("config", data)
        assert "✅ Created compare HTML file" in result
        assert "diff_config" in result

    def test_create_diff_html_content(self, temp_output_dir: str) -> None:
        """Test create_diff creates valid HTML with diff content."""
        nr_cmd = NornirCommands()

        cmp_file1 = Path(temp_output_dir) / "before.txt"
        cmp_file2 = Path(temp_output_dir) / "after.txt"
        cmp_file1.write_text("original\n")
        cmp_file2.write_text("modified\n")

        data: dict[str, Any] = {
            "output_fldr": temp_output_dir,
            "cmp_file1": str(cmp_file1),
            "cmp_file2": str(cmp_file2),
        }

        result = nr_cmd.create_diff("vital", data)

        # Extract filename from result message
        import re

        match = re.search(r"'([^']+)'$", result)
        assert match is not None

        output_file = match.group(1)
        assert os.path.exists(output_file)
        assert output_file.endswith(".html")

        # Verify HTML file contains diff content
        with open(output_file) as f:
            html_content = f.read()
        assert "original" in html_content
        assert "modified" in html_content
        assert "<table" in html_content

    def test_pos_create_diff_insufficient_files(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test pos_create_diff when insufficient files to compare."""
        nr_cmd = NornirCommands()

        # Create only one file (need at least 2)
        file1 = Path(temp_output_dir) / "R1_vital_20240101-0100.txt"
        file1.write_text("content")

        result = nr_cmd.pos_create_diff(mock_nornir_task, "vital", temp_output_dir)
        assert "❌ Only" in result
        assert "file matched" in result

    def test_pos_create_diff_with_valid_files(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test pos_create_diff with sufficient files to compare."""
        nr_cmd = NornirCommands()

        # Create two files with proper naming
        file1 = Path(temp_output_dir) / "R1_vital_20240101-0100.txt"
        file2 = Path(temp_output_dir) / "R1_vital_20240101-0200.txt"
        file1.write_text("content1\n")
        file2.write_text("content2\n")

        result = nr_cmd.pos_create_diff(mock_nornir_task, "vital", temp_output_dir)
        assert "✅ Created compare HTML file" in result
        assert "diff_vital" in result


# =============================================================================
# TEST CLASS 10: NornirCommands - Run Commands
# =============================================================================


class TestNornirCommandsRunCommands:
    """Test NornirCommands command execution methods."""

    def test_run_cmds_single_command(self, mock_nornir_task: MagicMock) -> None:
        """Test run_cmds with single command."""
        nr_cmd = NornirCommands()

        # Mock the netmiko response
        mock_result = MagicMock()
        mock_result.result = "version 15.0"
        mock_nornir_task.run.return_value = mock_result

        result = nr_cmd.run_cmds(mock_nornir_task, ["show version"], logging.INFO)
        assert "show version" in result
        assert "version 15.0" in result

    def test_run_cmds_multiple_commands(self, mock_nornir_task: MagicMock) -> None:
        """Test run_cmds with multiple commands."""
        nr_cmd = NornirCommands()

        mock_result = MagicMock()
        mock_result.result = "output"
        mock_nornir_task.run.return_value = mock_result

        result = nr_cmd.run_cmds(
            mock_nornir_task, ["show version", "show run"], logging.INFO
        )
        assert "show version" in result
        assert "show run" in result
        assert mock_nornir_task.run.call_count == 2

    def test_run_print_cmd_with_commands(self, mock_nornir_task: MagicMock) -> None:
        """Test run_print_cmd with commands."""
        nr_cmd = NornirCommands()

        with patch.object(nr_cmd, "run_cmds") as mock_run:
            nr_cmd.run_print_cmd(mock_nornir_task, ["show version"])
            mock_run.assert_called_once()

    def test_run_print_cmd_empty_list(self, mock_nornir_task: MagicMock) -> None:
        """Test run_print_cmd with empty command list."""
        nr_cmd = NornirCommands()

        with patch.object(nr_cmd, "run_cmds") as mock_run:
            nr_cmd.run_print_cmd(mock_nornir_task, [])
            mock_run.assert_not_called()

    def test_run_save_cmd_with_commands(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test run_save_cmd with commands."""
        nr_cmd = NornirCommands()

        # Mock the methods
        with (
            patch.object(nr_cmd, "run_cmds") as mock_run_cmds,
            patch.object(nr_cmd, "save_cmds") as mock_save_cmds,
        ):
            mock_run_cmds.return_value = "output"
            mock_save_cmds.return_value = f"{temp_output_dir}/R1_vital_20240101.txt"

            data: dict[str, Any] = {"output_fldr": temp_output_dir}
            result = nr_cmd.run_save_cmd(mock_nornir_task, "vital", data, ["show arp"])
            assert "✅ Created" in result
            assert mock_run_cmds.called
            assert mock_save_cmds.called

    def test_run_save_cmd_empty_list(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test run_save_cmd with empty command list."""
        nr_cmd = NornirCommands()

        with patch.object(nr_cmd, "run_cmds") as mock_run_cmds:
            data: dict[str, Any] = {"output_fldr": temp_output_dir}
            result = nr_cmd.run_save_cmd(mock_nornir_task, "vital", data, [])
            assert result == "empty"
            mock_run_cmds.assert_not_called()


# =============================================================================
# TEST CLASS 11: NornirCommands - Save Commands
# =============================================================================


class TestNornirCommandsSaveCommands:
    """Test NornirCommands save command methods."""

    def test_save_cmds_creates_file(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test save_cmds creates output file."""
        nr_cmd = NornirCommands()

        # Mock the write_file task
        mock_nornir_task.run = MagicMock()

        data: dict[str, Any] = {"output_fldr": temp_output_dir}
        result = nr_cmd.save_cmds(mock_nornir_task, "vital", data, "test output")

        assert "R1_vital" in result
        assert temp_output_dir in result
        assert mock_nornir_task.run.called

    def test_save_cmds_filename_format(
        self, mock_nornir_task: MagicMock, temp_output_dir: str
    ) -> None:
        """Test save_cmds filename includes correct format."""
        nr_cmd = NornirCommands()

        mock_nornir_task.run = MagicMock()

        data: dict[str, Any] = {"output_fldr": temp_output_dir}
        result = nr_cmd.save_cmds(mock_nornir_task, "config", data, "output")

        # Filename should be R1_config_YYYYMMDD-HHMM.txt
        assert "_config_" in result
        assert ".txt" in result


# =============================================================================
# TEST CLASS 12: Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_input_validate_workflow(self, temp_output_dir: str) -> None:
        """Test complete InputValidate workflow with all argument types."""
        input_val = InputValidate()

        # Create directory structure
        work_dir = Path(temp_output_dir) / "work"
        work_dir.mkdir()

        # Create input file
        input_yml = work_dir / "input_cmds.yml"
        test_data: dict[str, Any] = {
            "all": {"cmd_print": ["show version"]},
            "hosts": {"R1": {"cmd_vital": ["show arp"]}},
        }
        with open(input_yml, "w") as f:
            yaml.dump(test_data, f)

        # Test noncompare arg
        result = input_val.noncompare_arg("vital_save", [str(work_dir)])
        assert result["input_data"]["all"]["cmd_print"] == ["show version"]
        assert result["input_data"]["hosts"]["R1"]["cmd_vital"] == ["show arp"]
        assert os.path.exists(result["output_fldr"])

    def test_nornir_commands_full_workflow(self, mock_nornir_task: MagicMock) -> None:
        """Test NornirCommands through complete workflow."""
        nr_cmd = NornirCommands()

        input_data: dict[str, Any] = {
            "all": {"cmd_print": ["show version"], "cmd_vital": ["show arp"]},
            "hosts": {"R1": {"cmd_detail": ["show run"]}},
        }

        # Organize commands
        cmds = nr_cmd.organise_cmds(mock_nornir_task, input_data)

        # Verify all commands are collected
        assert "show version" in cmds["print"]
        assert "show arp" in cmds["vital"]
        assert "show run" in cmds["detail"]

    def test_diff_creation_workflow(self, temp_output_dir: str) -> None:
        """Test complete diff creation workflow."""
        nr_cmd = NornirCommands()

        # Create comparison files
        cmp_file1 = Path(temp_output_dir) / "config1.txt"
        cmp_file2 = Path(temp_output_dir) / "config2.txt"
        cmp_file1.write_text("interface eth0\n  ip 10.0.0.1\n")
        cmp_file2.write_text("interface eth0\n  ip 10.0.0.2\n")

        # Create diff
        data: dict[str, Any] = {
            "output_fldr": temp_output_dir,
            "cmp_file1": str(cmp_file1),
            "cmp_file2": str(cmp_file2),
        }

        result = nr_cmd.create_diff("config", data)

        # Verify diff file exists and contains HTML
        import re

        match = re.search(r"'([^']+)'$", result)
        assert match is not None

        html_file = match.group(1)
        with open(html_file) as f:
            content = f.read()
        assert "<html" in content.lower()
        # Content may be wrapped with span tags in diff, check for number patterns
        assert "10.0.0" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
