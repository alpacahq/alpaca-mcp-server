#!/usr/bin/env python3
"""
Alpaca MCP Server Installation Script
=====================================

This script automates the setup of the Alpaca MCP Server for Claude Desktop
by following the instructions in README.md.

Features:
- Creates and activates virtual environment
- Installs required dependencies
- Creates .env file with API key prompts
- Generates Claude Desktop configuration
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


def get_python_executable() -> str:
    """Get the appropriate Python executable name."""
    # Try different Python executable names
    python_names = ['python3', 'python']
    
    for name in python_names:
        try:
            result = subprocess.run([name, '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"   Found Python: {name} ({version})")
                return name
        except FileNotFoundError:
            continue
    
    print("   ❌ Error: Python not found. Please install Python 3.6+ first.")
    sys.exit(1)


def check_prerequisites():
    """Check if required tools are available."""
    print_step(1, "Checking Prerequisites")
    
    # Check Python
    python_cmd = get_python_executable()
    
    # Check Python version
    try:
        result = subprocess.run([python_cmd, '-c', 'import sys; print(sys.version_info[:2])'], 
                              capture_output=True, text=True)
        version_tuple = eval(result.stdout.strip())
        if version_tuple < (3, 6):
            print(f"   ❌ Error: Python {version_tuple[0]}.{version_tuple[1]} found, but Python 3.6+ is required")
            sys.exit(1)
        print(f"   ✅ Python {version_tuple[0]}.{version_tuple[1]} is compatible")
    except Exception as e:
        print(f"   ❌ Error checking Python version: {e}")
        sys.exit(1)
    
    print("   ✅ Prerequisites check completed")
    print()
    return python_cmd


def create_virtual_environment(python_cmd: str, project_dir: Path) -> Path:
    """Create and return path to virtual environment."""
    print_step(2, "Creating Virtual Environment")
    
    venv_path = project_dir / "myvenv"
    
    # Remove existing venv if it exists
    if venv_path.exists():
        print(f"   Removing existing virtual environment at {venv_path}")
        shutil.rmtree(venv_path)
    
    # Create virtual environment
    if not run_command([python_cmd, '-m', 'venv', str(venv_path)], 
                      "Create virtual environment"):
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


def install_dependencies(venv_path: Path, project_dir: Path):
    """Install required dependencies."""
    print_step(3, "Installing Dependencies")
    
    venv_python = get_venv_python(venv_path)
    requirements_file = project_dir / "requirements.txt"
    
    if not requirements_file.exists():
        print(f"   ❌ Error: requirements.txt not found at {requirements_file}")
        sys.exit(1)
    
    # Upgrade pip first
    if not run_command([str(venv_python), '-m', 'pip', 'install', '--upgrade', 'pip'], 
                      "Upgrade pip"):
        print("   ⚠️  Warning: Failed to upgrade pip, continuing anyway")
    
    # Install requirements
    if not run_command([str(venv_python), '-m', 'pip', 'install', '-r', str(requirements_file)], 
                      "Install requirements"):
        print("   ❌ Failed to install dependencies")
        sys.exit(1)
    
    print("   ✅ Dependencies installed successfully")
    print()


def prompt_for_api_keys() -> Dict[str, str]:
    """Prompt user for API keys and configuration."""
    print_step(4, "API Key Configuration")
    
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
    print_step(5, "Creating Environment File")
    
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


def generate_claude_config(project_dir: Path, venv_path: Path) -> Dict[str, Any]:
    """Generate Claude Desktop configuration."""
    print_step(6, "Generating Claude Desktop Configuration")
    
    # Get paths
    server_script = project_dir / "alpaca_mcp_server.py"
    venv_python = get_venv_python(venv_path)
    
    config = {
        "mcpServers": {
            "alpaca": {
                "command": str(venv_python),
                "args": [str(server_script)],
                "env": {
                    "ALPACA_API_KEY": "your_alpaca_api_key_for_paper_account",
                    "ALPACA_SECRET_KEY": "your_alpaca_secret_key_for_paper_account"
                }
            }
        }
    }
    
    print("   ✅ Claude Desktop configuration generated")
    print()
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


def backup_claude_config(config_path: Path) -> Optional[Path]:
    """Create a backup of the existing Claude config file."""
    if not config_path.exists():
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = config_path.parent / f"claude_desktop_config_backup_{timestamp}.json"
    
    try:
        shutil.copy2(config_path, backup_path)
        print(f"   📄 Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"   ⚠️  Warning: Could not create backup: {e}")
        return None


def load_claude_config(config_path: Path) -> Dict[str, Any]:
    """Load existing Claude Desktop configuration."""
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
        print(f"   ⚠️  Warning: Invalid JSON in Claude config: {e}")
        print(f"   Creating new configuration...")
        return {"mcpServers": {}}
    except Exception as e:
        print(f"   ⚠️  Warning: Could not read Claude config: {e}")
        return {"mcpServers": {}}


def update_claude_config(config_path: Path, alpaca_config: Dict[str, Any], api_config: Dict[str, str]) -> bool:
    """Update Claude Desktop configuration with Alpaca MCP server."""
    try:
        # Create config directory if it doesn't exist
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing config
        backup_claude_config(config_path)
        
        # Load existing configuration
        claude_config = load_claude_config(config_path)
        
        # Create Alpaca server config with actual API keys
        alpaca_server_config = alpaca_config["mcpServers"]["alpaca"].copy()
        if api_config['ALPACA_API_KEY'] and api_config['ALPACA_SECRET_KEY']:
            alpaca_server_config["env"] = {
                "ALPACA_API_KEY": api_config['ALPACA_API_KEY'],
                "ALPACA_SECRET_KEY": api_config['ALPACA_SECRET_KEY']
            }
        
        # Add or update Alpaca server configuration
        claude_config["mcpServers"]["alpaca"] = alpaca_server_config
        
        # Write updated configuration
        with open(config_path, 'w') as f:
            json.dump(claude_config, f, indent=2)
        
        print(f"   ✅ Claude Desktop config updated: {config_path}")
        return True
        
    except Exception as e:
        print(f"   ❌ Error updating Claude config: {e}")
        return False


def update_claude_desktop_config(claude_config: Dict[str, Any], api_config: Dict[str, str]):
    """Update Claude Desktop configuration automatically."""
    print_step(7, "Updating Claude Desktop Configuration")
    
    claude_config_path = get_claude_config_path()
    
    if not claude_config_path:
        print("   ⚠️  Could not determine Claude config path for this platform")
        return False
    
    print(f"   📁 Claude config location: {claude_config_path}")
    
    # Update automatically if API keys are provided
    if api_config['ALPACA_API_KEY'] and api_config['ALPACA_SECRET_KEY']:
        success = update_claude_config(claude_config_path, claude_config, api_config)
        if success:
            print("   🎉 Claude Desktop configuration updated successfully!")
            print("   📌 Next: Restart Claude Desktop to load the new configuration")
        else:
            print("   ⚠️  Manual configuration may be required")
        print()
        return success
    else:
        print("   ⏭️  Skipping automatic update (API keys not provided)")
        print("   💡 You can run the installer again with API keys to auto-configure")
        print()
        return False


def print_instructions(project_dir: Path, venv_path: Path, config: Dict[str, Any], auto_configured: bool = False):
    """Print final setup instructions."""
    step_num = 8 if auto_configured else 7
    print_step(step_num, "Setup Complete - Next Steps")
    
    # Get platform-specific paths
    claude_config_path = get_claude_config_path()
    server_script = project_dir / "alpaca_mcp_server.py"
    venv_python = get_venv_python(venv_path)
    
    print("   🎉 Alpaca MCP Server installation completed successfully!")
    print()
    
    if auto_configured:
        print("   ✅ Claude Desktop has been automatically configured!")
        print("   📋 Final Steps:")
        print()
        
        # Step 1: Restart Claude
        print("   1️⃣  Restart Claude Desktop")
        print("      Close and reopen Claude Desktop to load the new configuration")
        print()
        
        # Step 2: Test the integration
        print("   2️⃣  Test the integration:")
        print("      Open Claude Desktop and try asking:")
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
        print("   📋 Next Steps:")
        print()
        
        # Step 1: Configure API keys (if needed)
        print("   1️⃣  Configure your API keys (if not done already):")
        env_file = project_dir / ".env"
        print(f"      Edit {env_file}")
        print("      Add your Alpaca API keys")
        print()
        
        # Step 2: Test the server
        print("   2️⃣  Test the MCP server:")
        print(f"      cd {project_dir}")
        if platform.system() == "Windows":
            print(f"      {venv_path}\\Scripts\\activate")
        else:
            print(f"      source {venv_path}/bin/activate")
        print(f"      python {server_script.name}")
        print("      (Press Ctrl+C to stop)")
        print()
        
        # Step 3: Configure Claude Desktop manually
        print("   3️⃣  Configure Claude Desktop manually:")
        print(f"      Open Claude Desktop → Settings → Developer → Edit Config")
        if claude_config_path:
            print(f"      This should open: {claude_config_path}")
        print()
        print("      Add this configuration:")
        print("      " + "─" * 50)
        print(json.dumps(config, indent=6))
        print("      " + "─" * 50)
        print()
        
        # Step 4: Update paths and keys
        print("   4️⃣  Update the configuration:")
        print("      - Replace 'your_alpaca_api_key_for_paper_account' with your actual API key")
        print("      - Replace 'your_alpaca_secret_key_for_paper_account' with your actual secret key")
        print("      - Verify the paths are correct for your system")
        print()
        
        # Step 5: Restart Claude
        print("   5️⃣  Restart Claude Desktop")
        print("      Close and reopen Claude Desktop to load the new configuration")
        print()
    
    # Additional info (always shown)
    print("   💡 Additional Information:")
    print("      - The server uses paper trading by default (safe for testing)")
    print("      - To enable live trading, set ALPACA_PAPER_TRADE = False in .env")
    if auto_configured and claude_config_path:
        print(f"      - Configuration backup created in {claude_config_path.parent}")
    print("      - See README.md for more configuration options")
    print("      - For support, visit: https://github.com/alpacahq/alpaca-mcp-server")
    print()
    
    print("   ✅ Installation complete! Enjoy trading with Claude! 🚀")


def main():
    """Main installation function."""
    print_header()
    
    # Get project directory
    project_dir = Path(__file__).parent.absolute()
    print(f"Installing Alpaca MCP Server in: {project_dir}")
    print()
    
    try:
        # Check prerequisites
        python_cmd = check_prerequisites()
        
        # Create virtual environment
        venv_path = create_virtual_environment(python_cmd, project_dir)
        
        # Install dependencies
        install_dependencies(venv_path, project_dir)
        
        # Get API configuration
        api_config = prompt_for_api_keys()
        
        # Create .env file
        create_env_file(project_dir, api_config)
        
        # Generate Claude config
        claude_config = generate_claude_config(project_dir, venv_path)
        
        # Update Claude Desktop configuration
        auto_configured = update_claude_desktop_config(claude_config, api_config)
        
        # Print final instructions
        print_instructions(project_dir, venv_path, claude_config, auto_configured)
        
    except KeyboardInterrupt:
        print("\n\n❌ Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
