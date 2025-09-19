#!/bin/bash

# AICoder Installation Script
# Installs the AICoder AI Agent Development Toolkit

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ICON_SUCCESS="✅"
ICON_WARNING="⚠️"
ICON_INFO="ℹ️"
ICON_ROCKET="🚀"

VERSION="2.1.0"

echo -e "${BOLD}${CYAN}AICoder - AI Agent Development Toolkit v${VERSION}${NC}"
echo -e "${CYAN}Installing AICoder...${NC}"
echo ""

# Check if script is executable
if [ ! -x "aicoder.sh" ]; then
    echo -e "${YELLOW}${ICON_WARNING} Making aicoder.sh executable...${NC}"
    chmod +x aicoder.sh
fi

# Determine installation location
INSTALL_DIR="/usr/local/bin"
if [ "$EUID" -ne 0 ]; then
    # Not running as root, try user's bin directory
    if [ -d "$HOME/.local/bin" ]; then
        INSTALL_DIR="$HOME/.local/bin"
    else
        echo -e "${YELLOW}${ICON_WARNING} Not running as root. Installing to current directory.${NC}"
        echo -e "${CYAN}${ICON_INFO} You can move it to your PATH later:${NC}"
        echo "  sudo cp aicoder.sh /usr/local/bin/aicoder"
        INSTALL_DIR="."
    fi
fi

# Copy the script
if [ "$INSTALL_DIR" = "." ]; then
    cp aicoder.sh aicoder
    echo -e "${GREEN}${ICON_SUCCESS} Copied aicoder.sh to ./aicoder${NC}"
else
    sudo cp aicoder.sh "$INSTALL_DIR/aicoder"
    echo -e "${GREEN}${ICON_SUCCESS} Installed to $INSTALL_DIR/aicoder${NC}"
fi

# Make sure it's executable
chmod +x "$INSTALL_DIR/aicoder"

# Test installation
if command -v aicoder >/dev/null 2>&1; then
    echo -e "${GREEN}${ICON_SUCCESS} Installation successful!${NC}"
    echo ""
    echo -e "${BOLD}Quick Start:${NC}"
    echo "  aicoder init          # Initialize new project"
    echo "  aicoder start         # Start development session"
    echo "  aicoder help          # Show all commands"
    echo ""
    echo -e "${CYAN}${ICON_ROCKET} Ready to build with AI!${NC}"
else
    echo -e "${YELLOW}${ICON_WARNING} Installation complete, but 'aicoder' command not found in PATH${NC}"
    echo -e "${CYAN}${ICON_INFO} You can run it directly:${NC}"
    echo "  ./aicoder help"
    echo ""
    echo -e "${CYAN}${ICON_INFO} Or add to your PATH:${NC}"
    echo "  export PATH=\"$PWD:\$PATH\""
    echo "  echo 'export PATH=\"$PWD:\$PATH\"' >> ~/.bashrc"
fi

echo ""
echo -e "${BOLD}Next Steps:${NC}"
echo "1. Run 'aicoder init' to set up a new project"
echo "2. Run 'aicoder start' to begin development"
echo "3. Check 'aicoder help' for all commands"
echo ""
echo -e "${CYAN}${ICON_INFO} For documentation, see: README.md${NC}" 