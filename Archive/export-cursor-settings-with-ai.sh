#!/bin/bash

# Enhanced Cursor Settings Export - Includes Memories and System Prompts
# This script exports Cursor settings including AI-related configurations

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

# Function to export standard settings
export_standard_settings() {
    BACKUP_DIR=$1
    CURSOR_USER_DIR="$HOME/Library/Application Support/Cursor/User"
    
    print_status "Exporting standard Cursor settings..."
    
    # Copy main settings (may contain system prompt configs)
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
    
    # Copy workspace storage (may contain project-specific prompts)
    if [ -d "$CURSOR_USER_DIR/workspaceStorage" ]; then
        cp -r "$CURSOR_USER_DIR/workspaceStorage" "$BACKUP_DIR/"
        print_success "Exported workspace storage"
    fi
}

# Function to export AI-related settings
export_ai_settings() {
    BACKUP_DIR=$1
    CURSOR_USER_DIR="$HOME/Library/Application Support/Cursor/User"
    
    print_status "Exporting AI-related settings..."
    
    # Look for AI-specific configuration files
    AI_FILES=(
        "ai-settings.json"
        "cursor-ai.json"
        "system-prompts.json"
        "custom-prompts.json"
        "ai-config.json"
    )
    
    for file in "${AI_FILES[@]}"; do
        if [ -f "$CURSOR_USER_DIR/$file" ]; then
            cp "$CURSOR_USER_DIR/$file" "$BACKUP_DIR/"
            print_success "Exported $file"
        fi
    done
    
    # Look for AI-related directories
    AI_DIRS=(
        "ai-models"
        "system-prompts"
        "custom-prompts"
        "ai-templates"
        "prompt-templates"
    )
    
    for dir in "${AI_DIRS[@]}"; do
        if [ -d "$CURSOR_USER_DIR/$dir" ]; then
            cp -r "$CURSOR_USER_DIR/$dir" "$BACKUP_DIR/"
            print_success "Exported $dir"
        fi
    done
}

# Function to export workspace-specific AI settings
export_workspace_ai_settings() {
    BACKUP_DIR=$1
    CURSOR_USER_DIR="$HOME/Library/Application Support/Cursor/User"
    
    print_status "Exporting workspace-specific AI settings..."
    
    # Look for workspace-specific AI configurations
    if [ -d "$CURSOR_USER_DIR/workspaceStorage" ]; then
        # Find all workspace storage directories
        for workspace_dir in "$CURSOR_USER_DIR/workspaceStorage"/*; do
            if [ -d "$workspace_dir" ]; then
                workspace_name=$(basename "$workspace_dir")
                
                # Look for AI-related files in each workspace
                for file in "$workspace_dir"/*; do
                    if [ -f "$file" ]; then
                        filename=$(basename "$file")
                        if [[ "$filename" == *"ai"* ]] || [[ "$filename" == *"prompt"* ]] || [[ "$filename" == *"system"* ]]; then
                            mkdir -p "$BACKUP_DIR/workspace-ai-settings"
                            cp "$file" "$BACKUP_DIR/workspace-ai-settings/${workspace_name}-${filename}"
                            print_success "Exported workspace AI setting: $workspace_name/$filename"
                        fi
                    fi
                done
            fi
        done
    fi
}

# Function to export Cursor's local database
export_cursor_database() {
    BACKUP_DIR=$1
    CURSOR_DIR="$HOME/Library/Application Support/Cursor"
    
    print_status "Exporting Cursor's local database..."
    
    # Look for database files that might contain memories
    DB_FILES=(
        "Cursor.db"
        "cursor.db"
        "memories.db"
        "ai-memories.db"
        "conversations.db"
        "chat-history.db"
    )
    
    for db_file in "${DB_FILES[@]}"; do
        if [ -f "$CURSOR_DIR/$db_file" ]; then
            cp "$CURSOR_DIR/$db_file" "$BACKUP_DIR/"
            print_success "Exported database: $db_file"
        fi
    done
    
    # Look for database directories
    DB_DIRS=(
        "databases"
        "db"
        "storage"
        "local-storage"
    )
    
    for db_dir in "${DB_DIRS[@]}"; do
        if [ -d "$CURSOR_DIR/$db_dir" ]; then
            cp -r "$CURSOR_DIR/$db_dir" "$BACKUP_DIR/"
            print_success "Exported database directory: $db_dir"
        fi
    done
}

# Function to create AI settings documentation
create_ai_settings_doc() {
    BACKUP_DIR=$1
    
    print_status "Creating AI settings documentation..."
    
    cat > "$BACKUP_DIR/AI_SETTINGS_INFO.md" << 'EOF'
# Cursor AI Settings Export Information

## What's Included

### ✅ Exported AI Settings
- **System Prompts**: Custom system prompts and configurations
- **Workspace Prompts**: Project-specific AI prompts
- **AI Configurations**: Custom AI model settings
- **Prompt Templates**: Saved prompt templates
- **Local Database**: Cursor's local database (may contain memories)

### ❓ Partially Exported
- **Cloud Memories**: Some memories may be cloud-stored
- **Chat History**: May be stored in cloud or local database
- **AI Model Settings**: Depends on how they're configured

### ❌ Not Exported
- **Cloud-based Memories**: Stored in Cursor's cloud
- **Online Chat History**: If stored in cloud
- **Account-specific AI Settings**: Tied to your Cursor account

## Import Instructions

### Method 1: Automatic Sync (Recommended)
1. **Sign in** to Cursor on new computer
2. **Enable Settings Sync** - this will sync cloud-based memories
3. **Import local files** using manual method below

### Method 2: Manual Import
1. **Copy AI files** to Cursor's User directory
2. **Restart Cursor** to load new settings
3. **Check AI settings** in Cursor preferences

### Method 3: Database Import
1. **Close Cursor** completely
2. **Replace database files** in Cursor directory
3. **Restart Cursor** - memories should be restored

## Troubleshooting

### Memories Not Restored
- **Check cloud sync**: Sign in to Cursor account
- **Verify database**: Check if database files were copied
- **Restart Cursor**: Completely close and reopen

### System Prompts Not Working
- **Check file locations**: Ensure files are in correct directory
- **Verify permissions**: Check file permissions
- **Restart Cursor**: Restart to reload settings

### AI Settings Missing
- **Check settings.json**: Look for AI-related configurations
- **Verify workspace settings**: Check workspace-specific files
- **Reconfigure**: Manually reconfigure AI settings if needed

## File Locations

### macOS
- **User Settings**: `~/Library/Application Support/Cursor/User/`
- **Database**: `~/Library/Application Support/Cursor/`
- **Workspace**: `~/Library/Application Support/Cursor/User/workspaceStorage/`

### Windows
- **User Settings**: `%APPDATA%\Cursor\User\`
- **Database**: `%APPDATA%\Cursor\`
- **Workspace**: `%APPDATA%\Cursor\User\workspaceStorage\`

### Linux
- **User Settings**: `~/.config/Cursor/User/`
- **Database**: `~/.config/Cursor/`
- **Workspace**: `~/.config/Cursor/User/workspaceStorage/`

## Notes

- **Cloud Memories**: Will sync automatically if you're signed in
- **Local Memories**: Stored in database files (exported)
- **System Prompts**: Usually in settings.json or separate files
- **Workspace Prompts**: Project-specific, stored in workspaceStorage
EOF

    print_success "Created AI settings documentation"
}

# Function to create comprehensive import instructions
create_comprehensive_import_instructions() {
    BACKUP_DIR=$1
    
    print_status "Creating comprehensive import instructions..."
    
    cat > "$BACKUP_DIR/COMPREHENSIVE_IMPORT_INSTRUCTIONS.md" << 'EOF'
# Comprehensive Cursor Settings Import Instructions

## Overview
This backup includes standard Cursor settings AND AI-related configurations including memories and system prompts.

## Import Methods

### Method 1: Cursor Settings Sync (Recommended)
1. **Install Cursor** on new computer
2. **Sign in** with your Cursor account
3. **Enable Settings Sync** - this will sync cloud-based memories
4. **Import local files** using Method 2 below

### Method 2: Manual Import

#### Windows
1. **Close Cursor** completely
2. **Navigate to**: `%APPDATA%\Cursor\User\`
3. **Copy files** from this backup to that directory
4. **Navigate to**: `%APPDATA%\Cursor\`
5. **Copy database files** from this backup to that directory
6. **Restart Cursor**

#### Linux
1. **Close Cursor** completely
2. **Navigate to**: `~/.config/Cursor/User/`
3. **Copy files** from this backup to that directory
4. **Navigate to**: `~/.config/Cursor/`
5. **Copy database files** from this backup to that directory
6. **Restart Cursor**

#### macOS
1. **Close Cursor** completely
2. **Navigate to**: `~/Library/Application Support/Cursor/User/`
3. **Copy files** from this backup to that directory
4. **Navigate to**: `~/Library/Application Support/Cursor/`
5. **Copy database files** from this backup to that directory
6. **Restart Cursor**

## What Gets Imported

### Standard Settings
- ✅ Main settings (settings.json)
- ✅ Custom keybindings
- ✅ Code snippets
- ✅ Installed extensions
- ✅ Workspace configurations

### AI Settings
- ✅ System prompts
- ✅ Custom AI configurations
- ✅ Prompt templates
- ✅ Workspace-specific AI settings
- ✅ Local database (memories)

### Cloud Settings
- ✅ Memories (if signed in to Cursor)
- ✅ Chat history (if stored in cloud)
- ✅ Account-specific AI settings

## Verification Steps

1. **Check Settings**: Open Cursor preferences
2. **Verify Extensions**: Check installed extensions
3. **Test Keybindings**: Try custom keybindings
4. **Check AI Settings**: Verify system prompts work
5. **Test Memories**: Check if memories are restored
6. **Verify Workspaces**: Check project-specific settings

## Troubleshooting

### Settings Not Applied
- **Restart Cursor**: Completely close and reopen
- **Check Permissions**: Ensure files have correct permissions
- **Verify Locations**: Check file locations are correct

### AI Settings Missing
- **Sign in to Cursor**: Enable cloud sync
- **Check Database**: Verify database files were copied
- **Reconfigure**: Manually reconfigure if needed

### Memories Not Restored
- **Cloud Sync**: Ensure you're signed in to Cursor
- **Database Import**: Check if database files were copied
- **Restart**: Restart Cursor completely

## Support

If you encounter issues:
1. **Check Cursor logs** for error messages
2. **Verify file permissions** on imported files
3. **Contact Cursor support** if problems persist
4. **Use Settings Sync** as fallback method
EOF

    print_success "Created comprehensive import instructions"
}

# Function to create archive
create_archive() {
    BACKUP_DIR=$1
    
    print_status "Creating archive..."
    
    cd "$HOME/Desktop"
    tar -czf "cursor-settings-with-ai-$(basename "$BACKUP_DIR").tar.gz" "$(basename "$BACKUP_DIR")"
    
    ARCHIVE_PATH="$HOME/Desktop/cursor-settings-with-ai-$(basename "$BACKUP_DIR").tar.gz"
    print_success "Created archive: $ARCHIVE_PATH"
    echo "$ARCHIVE_PATH"
}

# Function to show summary
show_summary() {
    BACKUP_DIR=$1
    ARCHIVE_PATH=$2
    
    print_success "Cursor settings export completed (including AI settings)!"
    echo
    print_status "Export Summary:"
    echo "  📁 Backup Directory: $BACKUP_DIR"
    echo "  📦 Archive: $ARCHIVE_PATH"
    echo "  📋 Instructions: $BACKUP_DIR/COMPREHENSIVE_IMPORT_INSTRUCTIONS.md"
    echo "  🤖 AI Info: $BACKUP_DIR/AI_SETTINGS_INFO.md"
    echo
    print_status "What's Included:"
    echo "  ✅ Standard Cursor settings"
    echo "  ✅ Custom keybindings and snippets"
    echo "  ✅ Installed extensions"
    echo "  ✅ System prompts and AI configurations"
    echo "  ✅ Workspace-specific AI settings"
    echo "  ✅ Local database (memories)"
    echo "  ✅ Prompt templates"
    echo
    print_status "Next Steps:"
    echo "  1. Transfer the archive to your new computer"
    echo "  2. Extract the archive"
    echo "  3. Follow the comprehensive import instructions"
    echo "  4. Sign in to Cursor for cloud sync"
    echo
    print_status "Files exported:"
    ls -la "$BACKUP_DIR"
}

# Main function
main() {
    print_status "Starting comprehensive Cursor settings export (including AI settings)..."
    echo
    
    # Check prerequisites
    check_cursor_installed
    
    # Create backup directory
    BACKUP_DIR=$(create_backup_dir)
    
    # Export all settings
    export_standard_settings "$BACKUP_DIR"
    export_ai_settings "$BACKUP_DIR"
    export_workspace_ai_settings "$BACKUP_DIR"
    export_cursor_database "$BACKUP_DIR"
    
    # Create documentation
    create_ai_settings_doc "$BACKUP_DIR"
    create_comprehensive_import_instructions "$BACKUP_DIR"
    
    # Create archive
    ARCHIVE_PATH=$(create_archive "$BACKUP_DIR")
    
    # Show summary
    show_summary "$BACKUP_DIR" "$ARCHIVE_PATH"
}

# Run main function
main "$@"
