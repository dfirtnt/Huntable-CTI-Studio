#!/bin/bash

# Automated Backup Setup Script for CTI Scraper
# This script sets up automated daily backups with retention management

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_BACKUP_TIME="2:00"
DEFAULT_CLEANUP_TIME="3:00"
DEFAULT_BACKUP_DIR="backups"
DEFAULT_RETENTION_DAILY=7
DEFAULT_RETENTION_WEEKLY=4
DEFAULT_RETENTION_MONTHLY=3
DEFAULT_MAX_SIZE_GB=50

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --backup-time <time>        Backup time (HH:MM format, default: 2:00)"
    echo "  --cleanup-time <time>       Cleanup time (HH:MM format, default: 3:00)"
    echo "  --backup-dir <dir>          Backup directory (default: backups)"
    echo "  --daily <N>                 Keep last N daily backups (default: 7)"
    echo "  --weekly <N>                Keep last N weekly backups (default: 4)"
    echo "  --monthly <N>               Keep last N monthly backups (default: 3)"
    echo "  --max-size-gb <N>           Maximum total backup size in GB (default: 50)"
    echo "  --uninstall                 Remove automated backups"
    echo "  --status                    Show current backup status"
    echo "  --help                      Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                          # Setup with default settings"
    echo "  $0 --backup-time 1:30       # Setup with custom backup time"
    echo "  $0 --daily 10 --weekly 5    # Setup with custom retention"
    echo "  $0 --uninstall              # Remove automated backups"
    echo "  $0 --status                 # Show current status"
}

# Function to validate time format
validate_time() {
    local time=$1
    if [[ ! $time =~ ^[0-9]{1,2}:[0-9]{2}$ ]]; then
        print_error "Invalid time format: $time. Use HH:MM format (e.g., 2:00)"
        exit 1
    fi
    
    local hour=$(echo $time | cut -d: -f1)
    local minute=$(echo $time | cut -d: -f2)
    
    if [ $hour -gt 23 ] || [ $minute -gt 59 ]; then
        print_error "Invalid time: $time. Hour must be 0-23, minute must be 0-59"
        exit 1
    fi
}

# Function to check if running as root
check_root() {
    if [ "$EUID" -eq 0 ]; then
        print_warning "Running as root. This will install system-wide cron jobs."
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# Function to get project directory
get_project_dir() {
    local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    echo "$(dirname "$script_dir")"
}

# Function to check if cron is available
check_cron() {
    if ! command -v crontab &> /dev/null; then
        print_error "crontab command not found. Please install cron."
        exit 1
    fi
}

# Function to setup automated backups
setup_automated_backups() {
    local backup_time=$1
    local cleanup_time=$2
    local backup_dir=$3
    local daily=$4
    local weekly=$5
    local monthly=$6
    local max_size_gb=$7
    
    print_header "Setting up Automated Backups"
    
    # Get project directory
    local project_dir=$(get_project_dir)
    print_status "Project directory: $project_dir"
    
    # Validate inputs
    validate_time "$backup_time"
    validate_time "$cleanup_time"
    
    # Check prerequisites
    check_cron
    
    # Create backup directory if it doesn't exist
    if [ ! -d "$project_dir/$backup_dir" ]; then
        print_status "Creating backup directory: $project_dir/$backup_dir"
        mkdir -p "$project_dir/$backup_dir"
    fi
    
    # Convert time to cron format
    local backup_hour=$(echo $backup_time | cut -d: -f1)
    local backup_minute=$(echo $backup_time | cut -d: -f2)
    local cleanup_hour=$(echo $cleanup_time | cut -d: -f1)
    local cleanup_minute=$(echo $cleanup_time | cut -d: -f2)
    
    # Create cron job entries
    local backup_cron="$backup_minute $backup_hour * * * cd $project_dir && ./scripts/backup_restore.sh create --type full >> logs/backup.log 2>&1"
    local cleanup_cron="$cleanup_minute $cleanup_hour * * 0 cd $project_dir && ./scripts/backup_restore.sh prune --daily $daily --weekly $weekly --monthly $monthly --max-size-gb $max_size_gb --force >> logs/backup.log 2>&1"
    
    # Get current crontab
    local current_crontab=$(crontab -l 2>/dev/null || echo "")
    
    # Remove existing CTI Scraper backup entries
    local new_crontab=$(echo "$current_crontab" | grep -v "CTI Scraper backup" | grep -v "scripts/backup_restore.sh")
    
    # Add new entries
    new_crontab+="
# CTI Scraper backup - Daily full system backup at $backup_time
$backup_cron

# CTI Scraper backup - Weekly cleanup at $cleanup_time
$cleanup_cron
"
    
    # Install new crontab
    echo "$new_crontab" | crontab -
    
    print_status "Automated backups configured successfully!"
    print_status "Daily backup: $backup_time (full system backup)"
    print_status "Weekly cleanup: $cleanup_time (retention policy enforcement)"
    print_status "Backup directory: $project_dir/$backup_dir"
    print_status "Retention: $daily daily + $weekly weekly + $monthly monthly backups"
    print_status "Max size: ${max_size_gb}GB"
    
    # Create logs directory if it doesn't exist
    if [ ! -d "$project_dir/logs" ]; then
        mkdir -p "$project_dir/logs"
    fi
    
    # Create initial backup
    print_status "Creating initial backup..."
    cd "$project_dir"
    ./scripts/backup_restore.sh create --type full
    
    print_status "Setup complete! Check logs/backup.log for backup activity."
}

# Function to uninstall automated backups
uninstall_automated_backups() {
    print_header "Uninstalling Automated Backups"
    
    # Get current crontab
    local current_crontab=$(crontab -l 2>/dev/null || echo "")
    
    # Remove CTI Scraper backup entries
    local new_crontab=$(echo "$current_crontab" | grep -v "CTI Scraper backup" | grep -v "scripts/backup_restore.sh")
    
    # Install cleaned crontab
    echo "$new_crontab" | crontab -
    
    print_status "Automated backups removed successfully!"
    print_warning "Existing backup files are preserved. Remove manually if needed."
}

# Function to show backup status
show_backup_status() {
    print_header "Backup Status"
    
    # Get project directory
    local project_dir=$(get_project_dir)
    
    # Check crontab for backup entries
    local crontab_entries=$(crontab -l 2>/dev/null | grep "scripts/backup_restore.sh" || echo "")
    
    if [ -z "$crontab_entries" ]; then
        print_warning "No automated backups configured"
    else
        print_status "Automated backups are configured:"
        echo "$crontab_entries"
    fi
    
    # Show recent backups
    print_status "Recent backups:"
    cd "$project_dir"
    ./scripts/backup_restore.sh list
    
    # Show backup statistics
    print_status "Backup statistics:"
    python3 scripts/prune_backups.py --stats
    
    # Check backup log
    if [ -f "$project_dir/logs/backup.log" ]; then
        print_status "Recent backup log entries:"
        tail -10 "$project_dir/logs/backup.log"
    else
        print_warning "No backup log found"
    fi
}

# Function to create systemd service (alternative to cron)
create_systemd_service() {
    local backup_time=$1
    local cleanup_time=$2
    local backup_dir=$3
    local daily=$4
    local weekly=$5
    local monthly=$6
    local max_size_gb=$7
    
    print_header "Creating Systemd Service (Alternative)"
    
    # Get project directory
    local project_dir=$(get_project_dir)
    
    # Create service file
    local service_file="/etc/systemd/system/cti-scraper-backup.service"
    local timer_file="/etc/systemd/system/cti-scraper-backup.timer"
    
    print_status "Creating systemd service files..."
    
    # Create backup service
    cat > "$service_file" << EOF
[Unit]
Description=CTI Scraper Automated Backup
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=$project_dir
ExecStart=$project_dir/scripts/backup_restore.sh create --type full
StandardOutput=append:$project_dir/logs/backup.log
StandardError=append:$project_dir/logs/backup.log

[Install]
WantedBy=multi-user.target
EOF
    
    # Create backup timer
    cat > "$timer_file" << EOF
[Unit]
Description=Run CTI Scraper backup daily
Requires=cti-scraper-backup.service

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF
    
    # Reload systemd and enable timer
    systemctl daemon-reload
    systemctl enable cti-scraper-backup.timer
    systemctl start cti-scraper-backup.timer
    
    print_status "Systemd service created and enabled!"
    print_status "Service: $service_file"
    print_status "Timer: $timer_file"
    print_status "Use 'systemctl status cti-scraper-backup.timer' to check status"
}

# Main script logic
main() {
    # Default values
    local backup_time="$DEFAULT_BACKUP_TIME"
    local cleanup_time="$DEFAULT_CLEANUP_TIME"
    local backup_dir="$DEFAULT_BACKUP_DIR"
    local daily="$DEFAULT_RETENTION_DAILY"
    local weekly="$DEFAULT_RETENTION_WEEKLY"
    local monthly="$DEFAULT_RETENTION_MONTHLY"
    local max_size_gb="$DEFAULT_MAX_SIZE_GB"
    local uninstall=false
    local status=false
    local help=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --backup-time)
                backup_time="$2"
                shift 2
                ;;
            --cleanup-time)
                cleanup_time="$2"
                shift 2
                ;;
            --backup-dir)
                backup_dir="$2"
                shift 2
                ;;
            --daily)
                daily="$2"
                shift 2
                ;;
            --weekly)
                weekly="$2"
                shift 2
                ;;
            --monthly)
                monthly="$2"
                shift 2
                ;;
            --max-size-gb)
                max_size_gb="$2"
                shift 2
                ;;
            --uninstall)
                uninstall=true
                shift
                ;;
            --status)
                status=true
                shift
                ;;
            --help)
                help=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Handle help
    if [ "$help" = true ]; then
        show_usage
        exit 0
    fi
    
    # Handle status
    if [ "$status" = true ]; then
        show_backup_status
        exit 0
    fi
    
    # Handle uninstall
    if [ "$uninstall" = true ]; then
        uninstall_automated_backups
        exit 0
    fi
    
    # Setup automated backups
    setup_automated_backups "$backup_time" "$cleanup_time" "$backup_dir" "$daily" "$weekly" "$monthly" "$max_size_gb"
}

# Run main function
main "$@"
