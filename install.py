#!/usr/bin/env python3
"""
Alpaca MCP Server Installation Script
=====================================

This script automates the setup of the Alpaca MCP Server for Claude Desktop
or Cursor IDE by following the instructions in README.md.

Features:
- Checks for and installs uv (modern Python package manager)
- Creates virtual environment with Python 3.10+
- Installs required dependencies using uv
- Creates .env file with API key prompts
- Generates MCP client configuration
- Cross-platform support (macOS, Linux, Windows)
"""

import os
import sys
import subprocess
import platform
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


def print_header():
    """Print installation header."""
    print("=" * 60)
    print("🚀 Alpaca MCP Server Installation Script")
    print("=" * 60)
    print()


def print_step(step_num: int, description: str):
    """Print a step in the installation process."""
    print(f"📋 Step {step_num}: {description}")
    print("-" * 40)


def run_command(cmd: list, description: str, cwd: Optional[str] = None) -> bool:
    """Run a command and handle errors."""
    try:
        print(f"   Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, 
            check=True, 
            capture_output=True, 
            text=True, 
            cwd=cwd
        )
        if result.stdout:
            print(f"   Output: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Error: {description} failed")
        print(f"   Command: {' '.join(cmd)}")
        print(f"   Error output: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"   ❌ Error: Command not found: {cmd[0]}")
        return False


UV_INSTALL_DOC_URL = "https://docs.astral.sh/uv/getting-started/installation/"


def is_uv_installed() -> Optional[str]:
    """Return the path to uv if installed.

    This probes common installation locations and augments PATH in-process
    so the current script can use uv immediately after installation
    without requiring a shell restart.
    """
    # Fast path: respect current PATH first
    found = shutil.which("uv")
    if found:
        return found

    system = platform.system()
    home = Path.home()

    # Candidate directories commonly used by installers
    candidate_dirs = []
    if system == "Windows":
        candidate_dirs = [
            str(home / ".local" / "bin"),
            # Common Scripts location for per-user installs
            str(Path(os.environ.get("USERPROFILE", str(home))) / "AppData" / "Local" / "Programs" / "Python" / "Scripts"),
        ]
        candidate_files = [str(Path(d) / "uv.exe") for d in candidate_dirs]
    else:
        candidate_dirs = [
            "/opt/homebrew/bin",  # Apple Silicon Homebrew default
            "/usr/local/bin",     # Intel macOS and many Linux distros
            str(home / ".local" / "bin"),  # astral install.sh default
        ]
        candidate_files = [str(Path(d) / "uv") for d in candidate_dirs]

    # Temporarily augment PATH for this process and retry which()
    current_path = os.environ.get("PATH", "")
    for d in candidate_dirs:
        if d and d not in current_path:
            current_path = f"{d}{os.pathsep}{current_path}" if current_path else d
    os.environ["PATH"] = current_path

    found = shutil.which("uv")
    if found:
        return found

    # Direct file existence check as a fallback
    for p in candidate_files:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def install_uv(method: str) -> bool:
    """Install uv using the selected method."""
    if method == "curl":
        return run_command(
            ["/bin/sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
            "Install uv via curl"
        )
    if method == "wget":
        return run_command(
            ["/bin/sh", "-c", "wget -qO- https://astral.sh/uv/install.sh | sh"],
            "Install uv via wget"
        )
    if method == "brew":
        return run_command(
            ["/usr/bin/env", "brew", "install", "uv"],
            "Install uv via Homebrew"
        )
    if method == "pipx":
        return run_command(
            ["/usr/bin/env", "pipx", "install", "uv"],
            "Install uv via pipx"
        )
    if method == "winget":
        return run_command(
            ["/usr/bin/env", "winget", "install", "--id=astral-sh.uv", "-e"],
            "Install uv via WinGet"
        )
    if method == "scoop":
        return run_command(
            ["/usr/bin/env", "scoop", "install", "main/uv"],
            "Install uv via Scoop"
        )
    return False


def ensure_uv_installed() -> str:
    """Ensure uv is installed, prompting the user to install it if necessary."""
    print_step(1, "Checking Prerequisites")

    uv_path = is_uv_installed()
    if uv_path:
        print(f"   ✅ Found uv: {uv_path}")
        print()
        return uv_path

    print("   ❌ uv not found on PATH.")
    print(f"   uv is recommended to install Python 3.10+ and project dependencies. See {UV_INSTALL_DOC_URL}")
    print("   Installation methods available:")
    print("   • curl, wget, brew (macOS/Linux)")
    print("   • pipx (cross-platform)")
    print("   • winget (Windows)")
    print("   • scoop (Windows)")

    install_methods = {"curl", "wget", "brew", "pipx", "winget", "scoop"}

    while True:
        choice = input("   Install uv now? Choose method [curl/wget/brew/pipx/winget/scoop] or type 'skip' to cancel: ").strip().lower()
        if choice == "skip":
            print("   ❌ uv installation skipped. Cannot continue without uv.")
            sys.exit(1)
        if choice not in install_methods:
            print("   Invalid choice. Please enter 'curl', 'wget', 'brew', 'pipx', 'winget', 'scoop', or 'skip'.")
            continue

        success = install_uv(choice)
        if not success:
            print("   ❌ uv installation failed. Please try another method.")
            continue

        uv_path = is_uv_installed()
        if uv_path:
            print(f"   ✅ uv installed successfully: {uv_path}")
            print()
            return uv_path

        print("   ❌ uv still not found on PATH after installation. Please ensure it is installed and try again.")




def check_prerequisites() -> str:
    """Ensure uv is available for virtual environment installation."""
    print_step(1, "Checking Prerequisites")
    uv_path = ensure_uv_installed()
    print("   ✅ Prerequisites check completed")
    print()
    return uv_path




def create_virtual_environment(uv_path: str, project_dir: Path) -> Path:
    """Create and return path to virtual environment using uv."""
    print_step(2, "Creating Virtual Environment")

    venv_path = project_dir / ".venv"

    if venv_path.exists():
        print(f"   Removing existing virtual environment at {venv_path}")
        shutil.rmtree(venv_path)

    create_cmd = [uv_path, "venv", "--python", "3.10", ".venv"]
    if not run_command(create_cmd, "Create virtual environment with uv", cwd=str(project_dir)):
        print("   ❌ Failed to create virtual environment")
        sys.exit(1)

    print(f"   ✅ Virtual environment created at {venv_path}")
    print()
    return venv_path


def get_venv_python(venv_path: Path) -> Path:
    """Get the Python executable path in the virtual environment."""
    system = platform.system()
    if system == "Windows":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"


def install_dependencies(uv_path: str, venv_path: Path, project_dir: Path):
    """Install required dependencies using uv in virtual environment."""
    print_step(3, "Installing Dependencies")

    requirements_file = project_dir / "requirements.txt"

    if not requirements_file.exists():
        print(f"   ❌ Error: requirements.txt not found at {requirements_file}")
        sys.exit(1)

    # Use uv pip install as specified in README.md manual steps
    # uv pip automatically detects and uses the .venv folder when run from project directory
    install_cmd = [
        uv_path,
        "pip",
        "install",
        "-r",
        str(requirements_file),
    ]

    if not run_command(install_cmd, "Install requirements with uv pip", cwd=str(project_dir)):
        print("   ❌ Failed to install dependencies")
        sys.exit(1)

    # Install the package itself in editable mode
    # This creates the 'alpaca-mcp-server' CLI command
    package_install_cmd = [
        uv_path,
        "pip",
        "install",
        "-e",
        ".",
    ]
    
    if not run_command(package_install_cmd, "Install alpaca-mcp-server package", cwd=str(project_dir)):
        print("   ❌ Failed to install alpaca-mcp-server package")
        sys.exit(1)

    print("   ✅ Dependencies and package installed successfully")
    print()




def prompt_for_client() -> str:
    """Prompt user to select which MCP client to configure."""
    print_step(4, "MCP Client Selection")
    
    available_clients = {
        "claude": "Claude Desktop",
        "cursor": "Cursor IDE"
    }
    
    print("   Which MCP client would you like to configure?")
    print("   (To configure multiple clients, run the script multiple times)")
    print()
    
    for key, name in available_clients.items():
        print(f"   • {name} (type '{key}')")
    print()
    
    while True:
        choice = input("   Enter your choice (claude or cursor): ").strip().lower()
        
        if choice in available_clients:
            print()
            print(f"   ✅ Selected: {available_clients[choice]}")
            print()
            return choice
        else:
            print("   Invalid choice. Please type 'claude' or 'cursor'.")
            continue


def prompt_for_api_keys() -> Dict[str, str]:
    """Prompt user for API keys and configuration."""
    print_step(5, "API Key Configuration")
    
    print("   Please enter your Alpaca API credentials.")
    print("   You can find these at: https://app.alpaca.markets/paper/dashboard/overview")
    print("   (Leave blank to configure later)")
    print()
    
    api_key = input("   Enter your ALPACA_API_KEY: ").strip()
    secret_key = input("   Enter your ALPACA_SECRET_KEY: ").strip()
    
    print()
    print("   Trading mode configuration:")
    print("   - Paper trading (recommended for testing): True")
    print("   - Live trading (real money): False")
    
    while True:
        paper_trade = input("   Use paper trading? [Y/n]: ").strip().lower()
        if paper_trade in ['', 'y', 'yes']:
            paper_trade_value = "True"
            break
        elif paper_trade in ['n', 'no']:
            paper_trade_value = "False"
            print("   ⚠️  WARNING: Live trading mode selected - this will use real money!")
            confirm = input("   Are you sure? [y/N]: ").strip().lower()
            if confirm in ['y', 'yes']:
                break
            else:
                continue
        else:
            print("   Please enter 'y' for yes or 'n' for no")
    
    return {
        'ALPACA_API_KEY': api_key,
        'ALPACA_SECRET_KEY': secret_key,
        'ALPACA_PAPER_TRADE': paper_trade_value,
        'TRADE_API_URL': 'None',
        'TRADE_API_WSS': 'None',
        'DATA_API_URL': 'None',
        'STREAM_DATA_WSS': 'None'
    }


def create_env_file(project_dir: Path, api_config: Dict[str, str]):
    """Create .env file with API configuration."""
    print_step(6, "Creating Environment File")
    
    env_file = project_dir / ".env"
    
    env_content = f"""# Alpaca MCP Server Configuration
# Generated by install.py

# Alpaca API Credentials
ALPACA_API_KEY = "{api_config['ALPACA_API_KEY']}"
ALPACA_SECRET_KEY = "{api_config['ALPACA_SECRET_KEY']}"

# Trading Configuration
ALPACA_PAPER_TRADE = {api_config['ALPACA_PAPER_TRADE']}

# API Endpoints (leave as None for defaults)
TRADE_API_URL = {api_config['TRADE_API_URL']}
TRADE_API_WSS = {api_config['TRADE_API_WSS']}
DATA_API_URL = {api_config['DATA_API_URL']}
STREAM_DATA_WSS = {api_config['STREAM_DATA_WSS']}
"""
    
    try:
        with open(env_file, 'w') as f:
            f.write(env_content)
        print(f"   ✅ Environment file created at {env_file}")
        
        if not api_config['ALPACA_API_KEY'] or not api_config['ALPACA_SECRET_KEY']:
            print(f"   ⚠️  Note: API keys are empty. Please edit {env_file} to add your credentials.")
    except Exception as e:
        print(f"   ❌ Error creating .env file: {e}")
        sys.exit(1)
    
    print()


def generate_mcp_config(project_dir: Path, venv_path: Path) -> Dict[str, Any]:
    """Generate MCP server configuration."""
    # Get CLI command path (installed by 'uv pip install -e .')
    system = platform.system()
    if system == "Windows":
        alpaca_cli = venv_path / "Scripts" / "alpaca-mcp-server.exe"
    else:
        alpaca_cli = venv_path / "bin" / "alpaca-mcp-server"
    
    command = str(alpaca_cli)
    
    config = {
        "mcpServers": {
            "alpaca": {
                "command": command,
                "args": ["serve"],
                "env": {
                    "ALPACA_API_KEY": "your_alpaca_api_key_for_paper_account",
                    "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_paper_account"
                }
            }
        }
    }
    
    return config


def get_claude_config_path() -> Optional[Path]:
    """Get the Claude Desktop config file path for the current platform."""
    system = platform.system()
    home = Path.home()
    
    if system == "Darwin":  # macOS
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        return home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"
    else:  # Linux and others
        return home / ".config" / "claude" / "claude_desktop_config.json"


def get_cursor_config_path() -> Optional[Path]:
    """Get the Cursor MCP config file path for the current platform."""
    system = platform.system()
    home = Path.home()
    
    if system == "Darwin":  # macOS
        return home / ".cursor" / "mcp.json"
    elif system == "Windows":
        return home / ".cursor" / "mcp.json"
    else:  # Linux and others
        return home / ".cursor" / "mcp.json"


def backup_config_file(config_path: Path, client_name: str) -> Optional[Path]:
    """Create a backup of the existing config file."""
    if not config_path.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"{client_name}_config_backup_{timestamp}.json"
    
    try:
        shutil.copy2(config_path, backup_path)
        print(f"   📄 Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"   ⚠️  Warning: Could not create backup: {e}")
        return None


def load_mcp_config(config_path: Path, client_name: str) -> Dict[str, Any]:
    """Load existing MCP configuration."""
    if not config_path.exists():
        return {"mcpServers": {}}
    
    try:
        with open(config_path, 'r') as f:
            content = f.read().strip()
            if not content:
                return {"mcpServers": {}}
            config = json.loads(content)
            
        # Ensure mcpServers section exists
        if "mcpServers" not in config:
            config["mcpServers"] = {}
            
        return config
    except json.JSONDecodeError as e:
        print(f"   ⚠️  Warning: Invalid JSON in {client_name} config: {e}")
        print(f"   Creating new configuration...")
        return {"mcpServers": {}}
    except Exception as e:
        print(f"   ⚠️  Warning: Could not read {client_name} config: {e}")
        return {"mcpServers": {}}


def update_mcp_config(config_path: Path, alpaca_config: Dict[str, Any], api_config: Dict[str, str], client_name: str) -> bool:
    """Update MCP client configuration with Alpaca MCP server."""
    try:
        # Create config directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing config
        backup_config_file(config_path, client_name)
        
        # Load existing configuration
        existing_config = load_mcp_config(config_path, client_name)
        
        # Create Alpaca server config with actual API keys
        alpaca_server_config = alpaca_config["mcpServers"]["alpaca"].copy()
        if api_config['ALPACA_API_KEY'] and api_config['ALPACA_SECRET_KEY']:
            alpaca_server_config["env"] = {
                "ALPACA_API_KEY": api_config['ALPACA_API_KEY'],
                "ALPACA_SECRET_KEY": api_config['ALPACA_SECRET_KEY']
            }
        
        # Add or update Alpaca server configuration
        existing_config["mcpServers"]["alpaca"] = alpaca_server_config
        
        # Write updated configuration
        with open(config_path, 'w') as f:
            json.dump(existing_config, f, indent=2)
        
        print(f"   ✅ {client_name.title()} config updated: {config_path}")
        return True
        
    except Exception as e:
        print(f"   ❌ Error updating {client_name} config: {e}")
        return False


def update_client_configuration(selected_client: str, mcp_config: Dict[str, Any], api_config: Dict[str, str]) -> bool:
    """Update MCP client configuration automatically."""
    print_step(7, f"Updating {selected_client.title()} Configuration")
    
    print(f"   🔧 Configuring {selected_client.title()}...")
    
    if selected_client == "claude":
        config_path = get_claude_config_path()
    elif selected_client == "cursor":
        config_path = get_cursor_config_path()
    else:
        print(f"   ❌ Unknown client: {selected_client}")
        return False
    
    if not config_path:
        print(f"   ⚠️  Could not determine {selected_client} config path for this platform")
        return False
    
    print(f"   📁 {selected_client.title()} config location: {config_path}")
    
    # Update automatically if API keys are provided
    if api_config['ALPACA_API_KEY'] and api_config['ALPACA_SECRET_KEY']:
        success = update_mcp_config(config_path, mcp_config, api_config, selected_client)
        if success:
            print(f"   🎉 {selected_client.title()} configuration updated successfully!")
            if selected_client == "claude":
                print("   📌 Next: Restart Claude Desktop to load the new configuration")
            elif selected_client == "cursor":
                print("   📌 Next: Restart Cursor IDE to load the new configuration")
        else:
            print(f"   ⚠️  {selected_client.title()} manual configuration may be required")
        print()
        return success
    else:
        print(f"   ⏭️  Skipping {selected_client} automatic update (API keys not provided)")
        print("   💡 You can run the installer again with API keys to auto-configure")
        print()
        return False


def print_instructions(project_dir: Path, venv_path: Path, config: Dict[str, Any], selected_client: str, config_success: bool):
    """Print final setup instructions."""
    print_step(8, "Setup Complete - Next Steps")
    
    server_script = project_dir / "src" / "alpaca_mcp_server" / "server.py"
    env_file = project_dir / ".env"
    client_name = selected_client.title()
    
    print("   🎉 Alpaca MCP Server installation completed successfully!")
    print()
    
    if config_success:
        print(f"   ✅ {client_name} automatically configured!")
        print()
        
        print("   📋 Final Steps:")
        print()
        
        # Step 1: Restart client
        if selected_client == "claude":
            print("   1️⃣  Restart Claude Desktop")
            print("      Close and reopen Claude Desktop to load the new configuration")
        elif selected_client == "cursor":
            print("   1️⃣  Restart Cursor IDE")
            print("      Close and reopen Cursor to load the new configuration")
        print()
        
        # Step 2: Test the integration
        print("   2️⃣  Test the integration:")
        print(f"      Try asking in {client_name}:")
        print('      "What is my Alpaca account balance?"')
        print('      "Show me my current positions"')
        print()
        
        # Step 3: Optional testing
        print("   3️⃣  Optional - Test the server manually:")
        print(f"      cd {project_dir}")
        if platform.system() == "Windows":
            print(f"      {venv_path}\\Scripts\\activate")
        else:
            print(f"      source {venv_path}/bin/activate")
        print(f"      python {server_script.name}")
        print("      (Press Ctrl+C to stop)")
        print()
        
    else:
        print(f"   📋 Manual Configuration Required for {client_name}:")
        print()
        
        # Step 1: API keys (if needed)
        print("   1️⃣  Configure API keys (if not done already):")
        print(f"      Edit {env_file}")
        print("      Add your Alpaca API keys")
        print()
        
        # Step 2: Client-specific instructions
        if selected_client == "claude":
            claude_config_path = get_claude_config_path()
            print("   2️⃣  Configure Claude Desktop:")
            print("      Open Claude Desktop → Settings → Developer → Edit Config")
            if claude_config_path:
                print(f"      This should open: {claude_config_path}")
            print("      Add this configuration and update the API keys:")
            print("      " + "─" * 50)
            print(json.dumps(config, indent=6))
            print("      " + "─" * 50)
            print()
            
        elif selected_client == "cursor":
            cursor_config_path = get_cursor_config_path()
            print("   2️⃣  Configure Cursor IDE:")
            if cursor_config_path:
                print(f"      Create or edit: {cursor_config_path}")
            print("      Add this configuration and update the API keys:")
            print("      " + "─" * 50)
            print(json.dumps(config, indent=6))
            print("      " + "─" * 50)
            print()
        
        # Step 3: Restart
        print(f"   3️⃣  Restart {client_name}")
        print(f"      Close and reopen {client_name} to load the new configuration")
        print()
    
    # Additional info (always shown)
    print("   💡 Additional Information:")
    print("      - The server uses paper trading by default (safe for testing)")
    print("      - To enable live trading, set ALPACA_PAPER_TRADE = False in .env")
    print("      - Dependencies installed in virtual environment (.venv)")
    if config_success:
        print("      - Configuration backup was created automatically")
    print("      - To configure additional clients, run this script again")
    print("      - See README.md for more configuration options")
    print("      - For support, visit: https://github.com/alpacahq/alpaca-mcp-server")
    print()
    
    # Final message
    print(f"   ✅ Installation complete! Enjoy trading with {client_name}! 🚀")


def main():
    """Main installation function."""
    print_header()
    
    # Get project directory
    project_dir = Path(__file__).parent.absolute()
    print(f"Installing Alpaca MCP Server in: {project_dir}")
    print()
    
    try:
        # Check uv prerequisites
        uv_path = check_prerequisites()
        
        # Create virtual environment
        venv_path = create_virtual_environment(uv_path, project_dir)
        
        # Install dependencies in virtual environment
        install_dependencies(uv_path, venv_path, project_dir)
        
        # Get client selection
        selected_client = prompt_for_client()
        
        # Get API configuration
        api_config = prompt_for_api_keys()
        
        # Create .env file
        create_env_file(project_dir, api_config)
        
        # Generate MCP config
        mcp_config = generate_mcp_config(project_dir, venv_path)
        
        # Update client configuration
        config_success = update_client_configuration(selected_client, mcp_config, api_config)
        
        # Print final instructions
        print_instructions(project_dir, venv_path, mcp_config, selected_client, config_success)
        
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
