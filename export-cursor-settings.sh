#!/bin/bash

# Cursor Settings Migration Script
# Export settings from macOS and prepare for import on another computer

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Cursor is installed
check_cursor_installed() {
    if [ ! -d "$HOME/Library/Application Support/Cursor" ]; then
        print_error "Cursor not found. Please install Cursor first."
        exit 1
    fi
    print_success "Cursor installation found"
}

# Function to create backup directory
create_backup_dir() {
    BACKUP_DIR="$HOME/Desktop/cursor-settings-backup"
    TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
    BACKUP_DIR_WITH_TIME="$BACKUP_DIR-$TIMESTAMP"
    
    mkdir -p "$BACKUP_DIR_WITH_TIME"
    print_success "Created backup directory: $BACKUP_DIR_WITH_TIME"
    echo "$BACKUP_DIR_WITH_TIME"
}

# Function to export settings
export_settings() {
    BACKUP_DIR=$1
    CURSOR_USER_DIR="$HOME/Library/Application Support/Cursor/User"
    
    print_status "Exporting Cursor settings..."
    
    # Copy main settings
    if [ -f "$CURSOR_USER_DIR/settings.json" ]; then
        cp "$CURSOR_USER_DIR/settings.json" "$BACKUP_DIR/"
        print_success "Exported settings.json"
    fi
    
    # Copy keybindings
    if [ -f "$CURSOR_USER_DIR/keybindings.json" ]; then
        cp "$CURSOR_USER_DIR/keybindings.json" "$BACKUP_DIR/"
        print_success "Exported keybindings.json"
    fi
    
    # Copy snippets
    if [ -d "$CURSOR_USER_DIR/snippets" ]; then
        cp -r "$CURSOR_USER_DIR/snippets" "$BACKUP_DIR/"
        print_success "Exported snippets"
    fi
    
    # Copy extensions
    if [ -d "$CURSOR_USER_DIR/extensions" ]; then
        cp -r "$CURSOR_USER_DIR/extensions" "$BACKUP_DIR/"
        print_success "Exported extensions"
    fi
    
    # Copy workspace storage
    if [ -d "$CURSOR_USER_DIR/workspaceStorage" ]; then
        cp -r "$CURSOR_USER_DIR/workspaceStorage" "$BACKUP_DIR/"
        print_success "Exported workspace storage"
    fi
    
    # Copy other important files
    for file in "tasks.json" "launch.json" "extensions.json"; do
        if [ -f "$CURSOR_USER_DIR/$file" ]; then
            cp "$CURSOR_USER_DIR/$file" "$BACKUP_DIR/"
            print_success "Exported $file"
        fi
    done
}

# Function to export extensions list
export_extensions_list() {
    BACKUP_DIR=$1
    
    print_status "Exporting extensions list..."
    
    # Create extensions list
    EXTENSIONS_FILE="$BACKUP_DIR/extensions-list.txt"
    
    if [ -d "$HOME/Library/Application Support/Cursor/User/extensions" ]; then
        ls "$HOME/Library/Application Support/Cursor/User/extensions" > "$EXTENSIONS_FILE"
        print_success "Exported extensions list to extensions-list.txt"
    fi
}

# Function to create import instructions
create_import_instructions() {
    BACKUP_DIR=$1
    
    print_status "Creating import instructions..."
    
    cat > "$BACKUP_DIR/IMPORT_INSTRUCTIONS.md" << 'EOF'
# Cursor Settings Import Instructions

## Method 1: Automatic Import (Recommended)

1. **Install Cursor** on the new computer
2. **Open Cursor** → `Cursor` menu → `Settings Sync`
3. **Sign in** with your GitHub/Microsoft account
4. **Enable sync** - settings will automatically download

## Method 2: Manual Import

### Windows
1. **Close Cursor** if running
2. **Navigate to**: `%APPDATA%\Cursor\User\`
3. **Copy files** from this backup to that directory
4. **Restart Cursor**

### Linux
1. **Close Cursor** if running
2. **Navigate to**: `~/.config/Cursor/User/`
3. **Copy files** from this backup to that directory
4. **Restart Cursor**

### macOS
1. **Close Cursor** if running
2. **Navigate to**: `~/Library/Application Support/Cursor/User/`
3. **Copy files** from this backup to that directory
4. **Restart Cursor**

## Method 3: Import Extensions Only

1. **Open Cursor** on new computer
2. **Command Palette**: `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
3. **Type**: `Extensions: Import Extensions`
4. **Select**: `extensions-list.txt` from this backup

## Files Included

- `settings.json` - Main Cursor settings
- `keybindings.json` - Custom keybindings
- `snippets/` - Code snippets
- `extensions/` - Installed extensions
- `workspaceStorage/` - Workspace-specific settings
- `extensions-list.txt` - List of installed extensions

## Troubleshooting

- **If settings don't apply**: Restart Cursor completely
- **If extensions don't install**: Use the extensions list to reinstall manually
- **If keybindings conflict**: Check for conflicts in Cursor settings

## Notes

- Some settings may need adjustment for different operating systems
- Extensions may need to be reinstalled if they're not compatible
- Workspace settings are project-specific and may not apply to all projects
EOF

    print_success "Created import instructions"
}

# Function to create archive
create_archive() {
    BACKUP_DIR=$1
    
    print_status "Creating archive..."
    
    cd "$HOME/Desktop"
    tar -czf "cursor-settings-$(basename "$BACKUP_DIR").tar.gz" "$(basename "$BACKUP_DIR")"
    
    ARCHIVE_PATH="$HOME/Desktop/cursor-settings-$(basename "$BACKUP_DIR").tar.gz"
    print_success "Created archive: $ARCHIVE_PATH"
    echo "$ARCHIVE_PATH"
}

# Function to show summary
show_summary() {
    BACKUP_DIR=$1
    ARCHIVE_PATH=$2
    
    print_success "Cursor settings export completed!"
    echo
    print_status "Export Summary:"
    echo "  📁 Backup Directory: $BACKUP_DIR"
    echo "  📦 Archive: $ARCHIVE_PATH"
    echo "  📋 Instructions: $BACKUP_DIR/IMPORT_INSTRUCTIONS.md"
    echo
    print_status "Next Steps:"
    echo "  1. Transfer the archive to your new computer"
    echo "  2. Extract the archive"
    echo "  3. Follow the import instructions"
    echo "  4. Or use Cursor's Settings Sync feature"
    echo
    print_status "Files exported:"
    ls -la "$BACKUP_DIR"
}

# Main function
main() {
    print_status "Starting Cursor settings export..."
    echo
    
    # Check prerequisites
    check_cursor_installed
    
    # Create backup directory
    BACKUP_DIR=$(create_backup_dir)
    
    # Export settings
    export_settings "$BACKUP_DIR"
    export_extensions_list "$BACKUP_DIR"
    create_import_instructions "$BACKUP_DIR"
    
    # Create archive
    ARCHIVE_PATH=$(create_archive "$BACKUP_DIR")
    
    # Show summary
    show_summary "$BACKUP_DIR" "$ARCHIVE_PATH"
}

# Run main function
main "$@"
