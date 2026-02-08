#!/usr/bin/env python3
"""
Test script to verify dashboard components work
"""

import sys
import os
import subprocess
import json
from pathlib import Path

def run_command(cmd, shell=True, timeout=5):
    """Run a shell command and return output"""
    try:
        result = subprocess.run(
            cmd if shell else cmd.split(),
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return f"ERROR: {e}", -1

def test_openclaw_status():
    """Test OpenClaw status detection"""
    print("Testing OpenClaw status detection...")
    
    output, code = run_command("pgrep -f 'openclaw.*gateway'")
    running = code == 0
    print(f"  Gateway running: {running}")
    
    if running:
        config_path = Path.home() / '.openclaw' / 'config.json'
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                model = config.get('defaultModel', 'unknown')
                print(f"  Model: {model}")
        else:
            print("  Config not found")
    
    return running

def test_system_stats():
    """Test system stats collection"""
    print("\nTesting system stats collection...")
    
    # CPU
    output, _ = run_command("top -bn1 | grep 'Cpu(s)' | awk '{print $2}'")
    print(f"  CPU output: {output}")
    
    # Memory
    output, _ = run_command("free -m | awk 'NR==2{print $3}'")
    print(f"  Memory: {output}M")
    
    # Temperature
    output, _ = run_command("cat /sys/class/thermal/thermal_zone0/temp")
    try:
        temp = int(output) / 1000.0
        print(f"  Temperature: {temp}°C")
    except:
        print(f"  Temperature: ERROR ({output})")
    
    return True

def test_todoist():
    """Test Todoist integration"""
    print("\nTesting Todoist integration...")
    
    token = os.environ.get('TODOIST_API_TOKEN')
    if not token:
        print("  ⚠️  TODOIST_API_TOKEN not set")
        print("  Dashboard will show 'No API token' message")
        return False
    
    print(f"  Token found: {token[:8]}...")
    
    output, code = run_command("todoist --csv tasks", timeout=8)
    if code != 0 or output == "TIMEOUT":
        print(f"  ⚠️  Failed to fetch tasks (code: {code})")
        return False
    
    lines = output.strip().split('\n')
    print(f"  Tasks fetched: {len(lines)-1} (including header)")
    
    return True

def test_pygame():
    """Test pygame availability"""
    print("\nTesting pygame...")
    
    try:
        import pygame
        print(f"  pygame version: {pygame.version.ver}")
        print(f"  SDL version: {pygame.version.SDL}")
        return True
    except ImportError as e:
        print(f"  ⚠️  pygame not available: {e}")
        return False

def test_display():
    """Test display configuration"""
    print("\nTesting display configuration...")
    
    display = os.environ.get('DISPLAY', 'not set')
    print(f"  DISPLAY: {display}")
    
    # Check framebuffers
    fb0 = Path('/dev/fb0').exists()
    fb1 = Path('/dev/fb1').exists()
    print(f"  /dev/fb0: {fb0}")
    print(f"  /dev/fb1: {fb1}")
    
    return display != 'not set'

def main():
    print("=" * 50)
    print("Pi 400 Dashboard - Component Test")
    print("=" * 50)
    
    results = {
        'pygame': test_pygame(),
        'display': test_display(),
        'openclaw': test_openclaw_status(),
        'system_stats': test_system_stats(),
        'todoist': test_todoist()
    }
    
    print("\n" + "=" * 50)
    print("Test Summary:")
    print("=" * 50)
    
    for component, status in results.items():
        icon = "✓" if status else "✗"
        print(f"  {icon} {component.replace('_', ' ').title()}: {'OK' if status else 'FAILED'}")
    
    all_ok = all(results.values())
    
    print("\n" + "=" * 50)
    if all_ok:
        print("All tests passed! Dashboard should work correctly.")
        print("\nRun: ./launch.sh")
    else:
        print("Some tests failed. Dashboard will run but with limited functionality.")
        print("\nMissing components will show error messages in the dashboard.")
    print("=" * 50)
    
    return 0 if all_ok else 1

if __name__ == '__main__':
    sys.exit(main())
