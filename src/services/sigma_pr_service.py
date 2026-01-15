"""
SIGMA PR Submission Service

Handles pushing approved SIGMA rules to external repository via GitHub PRs.
"""

import logging
import os
import re
import subprocess
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import httpx

logger = logging.getLogger(__name__)


class SigmaPRService:
    """Service for submitting SIGMA rules to external repository via GitHub PRs."""
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize the PR service.
        
        Args:
            repo_path: Path to local SIGMA repository. Defaults to ../Huntable-SIGMA-Rules
        """
        # Try to load from AppSettings first, then fall back to env vars
        self.github_token = self._get_setting("GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        # Default path: check if we're in Docker (sigma-repo mount) or local (../Huntable-SIGMA-Rules)
        default_path = "sigma-repo" if os.path.exists("/.dockerenv") or os.path.exists("/app/sigma-repo") else "../Huntable-SIGMA-Rules"
        repo_path_setting = self._get_setting("SIGMA_REPO_PATH") or os.getenv("SIGMA_REPO_PATH", default_path)
        
        # Resolve path: if relative, resolve from app root; if absolute, use as-is
        repo_path_str = repo_path or repo_path_setting
        if not repo_path_str:
            # Default fallback based on environment
            repo_path_str = "sigma-repo" if os.path.exists("/.dockerenv") or os.path.exists("/app/sigma-repo") else "../Huntable-SIGMA-Rules"
        
        # Clean up the path string (remove leading/trailing whitespace)
        repo_path_str = repo_path_str.strip()
        
        if os.path.isabs(repo_path_str):
            # Absolute path - use as-is
            self.repo_path = Path(repo_path_str)
        else:
            # Relative path - resolve from app root (parent of src/)
            app_root = Path(__file__).parent.parent.parent  # Go up from src/services/sigma_pr_service.py
            self.repo_path = (app_root / repo_path_str).resolve()
        
        logger.info(f"Resolved SIGMA repo path: {self.repo_path} (from input: '{repo_path_str}', exists: {self.repo_path.exists()})")
        
        # Warn if path doesn't exist (but don't fail yet - let submit_pr handle it)
        if not self.repo_path.exists():
            logger.warning(f"SIGMA repo path does not exist: {self.repo_path}. Please check your SIGMA_REPO_PATH setting.")
        
        self.github_repo = self._get_setting("GITHUB_REPO") or os.getenv("GITHUB_REPO", "dfirtnt/Huntable-SIGMA-Rules")
        self.rules_path = self.repo_path / "rules"
        
        if not self.github_token:
            logger.warning("GITHUB_TOKEN not set - PR creation will fail")
    
    def _get_setting(self, key: str) -> Optional[str]:
        """
        Get setting from AppSettings database table.
        
        Args:
            key: Setting key
            
        Returns:
            Setting value or None
        """
        try:
            from src.database.manager import DatabaseManager
            from src.database.models import AppSettingsTable
            
            db_manager = DatabaseManager()
            db_session = db_manager.get_session()
            
            try:
                setting = db_session.query(AppSettingsTable).filter(
                    AppSettingsTable.key == key
                ).first()
                
                if setting and setting.value:
                    return setting.value
            finally:
                db_session.close()
        except Exception as e:
            logger.debug(f"Could not load setting {key} from database: {e}")
        
        return None
    
    def _slugify_title(self, title: str) -> str:
        """
        Convert rule title to filename-safe slug.
        
        Args:
            title: Rule title
            
        Returns:
            Slugified string
        """
        # Convert to lowercase
        slug = title.lower()
        # Replace spaces and special chars with underscores
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '_', slug)
        # Remove leading/trailing underscores
        slug = slug.strip('_')
        # Limit length
        if len(slug) > 100:
            slug = slug[:100]
        return slug
    
    def _determine_file_path(self, rule_yaml: str) -> Tuple[Path, str]:
        """
        Determine file path and name from rule logsource.
        
        Args:
            rule_yaml: Rule YAML content
            
        Returns:
            Tuple of (full_path, filename)
        """
        try:
            rule_data = yaml.safe_load(rule_yaml)
            logsource = rule_data.get('logsource', {})
            
            # Determine directory from product/category
            product = logsource.get('product', '').lower() if logsource.get('product') else ''
            category = logsource.get('category', '').lower() if logsource.get('category') else ''
            
            # Map to directory
            if product == 'windows':
                directory = self.rules_path / 'windows'
            elif product == 'linux':
                directory = self.rules_path / 'linux'
            elif product == 'macos':
                directory = self.rules_path / 'macos'
            elif category == 'network':
                directory = self.rules_path / 'network'
            elif category == 'web':
                directory = self.rules_path / 'web'
            elif category == 'cloud' or product == 'cloud':
                directory = self.rules_path / 'cloud'
            else:
                # Default to windows
                directory = self.rules_path / 'windows'
            
            # Ensure directory exists
            directory.mkdir(parents=True, exist_ok=True)
            
            # Generate filename from title
            title = rule_data.get('title', 'untitled_rule')
            base_filename = self._slugify_title(title)
            filename = f"{base_filename}.yml"
            
            # Handle duplicates
            full_path = directory / filename
            counter = 1
            while full_path.exists():
                filename = f"{base_filename}_{counter}.yml"
                full_path = directory / filename
                counter += 1
            
            return full_path, filename
            
        except Exception as e:
            logger.error(f"Error determining file path: {e}")
            # Fallback
            directory = self.rules_path / 'windows'
            directory.mkdir(parents=True, exist_ok=True)
            filename = f"rule_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yml"
            return directory / filename, filename
    
    def _run_git_command(self, cmd: List[str], check: bool = True) -> Tuple[int, str, str]:
        """
        Run git command in repository.
        
        Args:
            cmd: Git command as list
            check: Raise exception on non-zero return code
            
        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        try:
            result = subprocess.run(
                ["git"] + cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if check and result.returncode != 0:
                raise Exception(f"Git command failed: {' '.join(cmd)}\n{result.stderr}")
            
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            raise Exception(f"Git command timed out: {' '.join(cmd)}")
        except Exception as e:
            logger.error(f"Git command error: {e}")
            raise
    
    def _configure_remote_auth(self) -> None:
        """
        Configure Git remote URL to include GitHub token for authentication.
        Updates the origin remote to use token-based authentication.
        """
        if not self.github_token:
            logger.warning("No GitHub token available - remote auth not configured")
            return
        
        try:
            # Get current remote URL
            returncode, stdout, stderr = self._run_git_command(["remote", "get-url", "origin"], check=False)
            if returncode != 0:
                logger.warning(f"Could not get remote URL: {stderr}")
                return
            
            current_url = stdout.strip()
            
            # Check if URL already contains token
            if self.github_token in current_url:
                logger.debug("Remote URL already contains token")
                return
            
            # Parse current URL and rebuild with token
            # Handle both https://github.com/owner/repo.git and git@github.com:owner/repo.git
            if current_url.startswith("https://"):
                # HTTPS URL - insert token
                if "@github.com" in current_url:
                    # Already has credentials, replace them
                    url_parts = current_url.split("@")
                    new_url = f"https://{self.github_token}@{url_parts[-1]}"
                else:
                    # No credentials, add token
                    new_url = current_url.replace("https://github.com", f"https://{self.github_token}@github.com")
                
                logger.info("Configuring remote URL with GitHub token for authentication")
                self._run_git_command(["remote", "set-url", "origin", new_url], check=False)
                logger.debug("Remote URL configured successfully")
            elif current_url.startswith("git@"):
                # SSH URL - no token needed, but log for info
                logger.debug("Remote uses SSH authentication (no token needed)")
            else:
                logger.warning(f"Unknown remote URL format: {current_url}")
        except Exception as e:
            logger.warning(f"Failed to configure remote auth: {e}")
    
    def _check_repo_status(self) -> Dict[str, Any]:
        """
        Check repository status and validate it's ready for PR.
        
        Returns:
            Status dictionary
        """
        if not self.repo_path.exists():
            return {
                "valid": False,
                "error": f"Repository path does not exist: {self.repo_path}"
            }
        
        if not (self.repo_path / ".git").exists():
            return {
                "valid": False,
                "error": f"Not a git repository: {self.repo_path}"
            }
        
        # Check for uncommitted changes (only modified tracked files, ignore untracked)
        _, stdout, _ = self._run_git_command(["status", "--porcelain"], check=False)
        # Filter to only modified/deleted/renamed tracked files (M=modified, A=added, D=deleted, R=renamed, C=copied)
        # Ignore untracked files (??) as they don't interfere
        modified_files = [line for line in stdout.strip().split('\n') if line and line[0] in 'MADRC']
        if modified_files:
            # Auto-stash changes to allow PR creation
            try:
                logger.info(f"Found {len(modified_files)} uncommitted changes, auto-stashing...")
                stash_message = f"Auto-stashed by CTI Studio before PR {datetime.now().strftime('%Y%m%d_%H%M%S')}"
                returncode, _, stash_err = self._run_git_command(["stash", "push", "-m", stash_message], check=False)
                if returncode == 0:
                    logger.info("Successfully stashed uncommitted changes")
                else:
                    # Stash might have failed (e.g., nothing to stash after all, or git error)
                    logger.warning(f"Git stash returned code {returncode}: {stash_err}")
                    # Verify if changes still exist
                    _, stdout_after, _ = self._run_git_command(["status", "--porcelain"], check=False)
                    modified_after = [line for line in stdout_after.strip().split('\n') if line and line[0] in 'MADRC']
                    if modified_after:
                        # Still have changes, stash failed
                        return {
                            "valid": False,
                            "error": f"Repository has uncommitted changes that could not be stashed automatically. Please commit or stash them manually first. Files: {', '.join([f.split()[-1] for f in modified_after[:3]])}"
                        }
            except Exception as e:
                logger.warning(f"Failed to stash changes: {e}")
                return {
                    "valid": False,
                    "error": f"Repository has uncommitted changes that could not be stashed: {str(e)}. Please commit or stash them manually first."
                }
        
        # Ensure we're on main/master
        _, stdout, _ = self._run_git_command(["branch", "--show-current"], check=False)
        current_branch = stdout.strip()
        if current_branch not in ['main', 'master']:
            return {
                "valid": False,
                "error": f"Not on main/master branch (currently on {current_branch})"
            }
        
        # Configure remote URL with token if using HTTPS
        self._configure_remote_auth()
        
        # Pull latest changes
        try:
            self._run_git_command(["pull", "origin", current_branch], check=False)
        except Exception as e:
            logger.warning(f"Failed to pull latest changes: {e}")
        
        return {"valid": True}
    
    def submit_pr(self, rules: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Submit approved rules as a GitHub PR.
        
        Args:
            rules: List of rule dictionaries with 'id' and 'rule_yaml' keys
            
        Returns:
            Result dictionary with PR URL and status
        """
        if not rules:
            return {
                "success": False,
                "error": "No rules provided"
            }
        
        # Validate repository exists
        if not self.repo_path.exists():
            # Provide helpful debugging info
            app_root = Path(__file__).parent.parent.parent
            # Check if parent directory exists
            parent_exists = self.repo_path.parent.exists() if self.repo_path.parent != self.repo_path else False
            
            # Check if we're in Docker
            in_docker = os.path.exists('/.dockerenv') or (os.path.exists('/proc/self/cgroup') and 'docker' in open('/proc/self/cgroup', 'r').read())
            docker_note = "\n\n⚠️ Note: If running in Docker, the path must exist inside the container. You may need to:\n- Mount the repository as a Docker volume\n- Use a path that exists inside the container\n- Or run the app outside Docker for local development" if in_docker else ""
            
            return {
                "success": False,
                "error": f"Repository path does not exist: {self.repo_path}\n\n"
                        f"Debug info:\n"
                        f"- App root: {app_root}\n"
                        f"- Parent directory exists: {parent_exists}\n"
                        f"- Parent path: {self.repo_path.parent}\n"
                        f"- Running in Docker: {in_docker}{docker_note}\n\n"
                        f"Please verify:\n"
                        f"1. The repository exists at this path\n"
                        f"2. The path in Settings is correct\n"
                        f"   - Relative: '../Huntable-SIGMA-Rules' (from app root)\n"
                        f"   - Absolute: '/Users/starlord/Huntable-SIGMA-Rules'\n"
                        f"3. You have read/write permissions to this directory\n"
                        f"4. After changing Settings, click 'Save Settings' and refresh the page"
            }
        
        # Validate repository
        repo_status = self._check_repo_status()
        if not repo_status.get("valid"):
            return {
                "success": False,
                "error": repo_status.get("error", "Repository validation failed")
            }
        
        if not self.github_token:
            return {
                "success": False,
                "error": "GITHUB_TOKEN not configured"
            }
        
        # Create branch
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        branch_name = f"sigma-rules-{timestamp}"
        
        try:
            # Configure git user if not already set (use local config for this repo only)
            try:
                # Get git config from settings or environment, with defaults
                git_email = self._get_setting("GIT_EMAIL") or os.getenv("GIT_EMAIL", "cti-studio@huntable.local")
                git_name = self._get_setting("GIT_NAME") or os.getenv("GIT_NAME", "Huntable CTI Studio")
                
                # Check if git config is already set in this repo
                _, email_out, _ = self._run_git_command(["config", "user.email"], check=False)
                _, name_out, _ = self._run_git_command(["config", "user.name"], check=False)
                
                # Set if not already configured
                if not email_out.strip():
                    self._run_git_command(["config", "user.email", git_email], check=False)
                    logger.info(f"Set git user.email to: {git_email}")
                else:
                    logger.debug(f"Git user.email already set to: {email_out.strip()}")
                
                if not name_out.strip():
                    self._run_git_command(["config", "user.name", git_name], check=False)
                    logger.info(f"Set git user.name to: {git_name}")
                else:
                    logger.debug(f"Git user.name already set to: {name_out.strip()}")
            except Exception as e:
                logger.warning(f"Could not configure git user: {e}")
                # Set defaults anyway
                self._run_git_command(["config", "user.email", "cti-studio@huntable.local"], check=False)
                self._run_git_command(["config", "user.name", "Huntable CTI Studio"], check=False)
            
            # Create and checkout branch
            self._run_git_command(["checkout", "-b", branch_name])
            
            # Write rules to files
            files_added = []
            for rule in rules:
                rule_yaml = rule.get('rule_yaml')
                if not rule_yaml:
                    logger.warning(f"Rule {rule.get('id')} has no YAML content, skipping")
                    continue
                
                full_path, filename = self._determine_file_path(rule_yaml)
                
                # Write file
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(rule_yaml)
                
                files_added.append({
                    'path': str(full_path.relative_to(self.repo_path)),
                    'filename': filename,
                    'rule_id': rule.get('id')
                })
            
            if not files_added:
                # No files to commit, cleanup branch
                # Determine base branch first
                _, stdout, _ = self._run_git_command(["branch", "-r"], check=False)
                base_branch = "main" if "origin/main" in stdout else "master"
                self._run_git_command(["checkout", base_branch], check=False)
                self._run_git_command(["branch", "-D", branch_name], check=False)
                return {
                    "success": False,
                    "error": "No valid rules to submit"
                }
            
            # Stage all files
            for file_info in files_added:
                self._run_git_command(["add", file_info['path']])
            
            # Commit
            commit_message = f"Add {len(files_added)} approved SIGMA rules from CTI Studio"
            self._run_git_command(["commit", "-m", commit_message])
            
            # Push branch
            self._run_git_command(["push", "-u", "origin", branch_name])
            
            # Create PR via GitHub API
            pr_url = self._create_github_pr(
                branch_name=branch_name,
                title=commit_message,
                body=self._generate_pr_body(files_added, rules)
            )
            
            if not pr_url:
                # PR creation failed, but branch is pushed
                # User can create PR manually
                return {
                    "success": False,
                    "error": "Failed to create PR via API, but branch was pushed",
                    "branch": branch_name,
                    "files_added": files_added
                }
            
            return {
                "success": True,
                "pr_url": pr_url,
                "branch": branch_name,
                "files_added": files_added,
                "rules_count": len(files_added)
            }
            
        except Exception as e:
            logger.error(f"Error submitting PR: {e}")
            # Try to cleanup branch
            try:
                # Determine base branch first
                _, stdout, _ = self._run_git_command(["branch", "-r"], check=False)
                base_branch = "main" if "origin/main" in stdout else "master"
                self._run_git_command(["checkout", base_branch], check=False)
                self._run_git_command(["branch", "-D", branch_name], check=False)
            except:
                pass
            
            return {
                "success": False,
                "error": str(e)
            }
    
    def _generate_pr_body(self, files_added: List[Dict], rules: List[Dict]) -> str:
        """Generate PR description body."""
        body = f"## Summary\n\n"
        body += f"This PR adds {len(files_added)} approved SIGMA detection rules from Huntable CTI Studio.\n\n"
        body += f"## Rules Added\n\n"
        
        for file_info in files_added:
            rule_id = file_info.get('rule_id')
            rule = next((r for r in rules if r.get('id') == rule_id), None)
            if rule:
                try:
                    rule_data = yaml.safe_load(rule.get('rule_yaml', ''))
                    title = rule_data.get('title', 'Unknown')
                    body += f"- **{title}** (`{file_info['filename']}`)\n"
                except:
                    body += f"- `{file_info['filename']}`\n"
        
        body += f"\n## Files Changed\n\n"
        for file_info in files_added:
            body += f"- `{file_info['path']}`\n"
        
        body += f"\n---\n\n*Generated automatically by Huntable CTI Studio*"
        return body
    
    def _create_github_pr(
        self,
        branch_name: str,
        title: str,
        body: str
    ) -> Optional[str]:
        """
        Create GitHub PR via API.
        
        Args:
            branch_name: Branch name
            title: PR title
            body: PR body
            
        Returns:
            PR URL or None on failure
        """
        try:
            repo_owner, repo_name = self.github_repo.split('/')
            
            url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/pulls"
            headers = {
                "Authorization": f"token {self.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "Content-Type": "application/json"
            }
            
            # Determine base branch (main or master)
            _, stdout, _ = self._run_git_command(["branch", "-r"], check=False)
            base_branch = "main" if "origin/main" in stdout else "master"
            
            payload = {
                "title": title,
                "body": body,
                "head": branch_name,
                "base": base_branch
            }
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, json=payload)
                
                if response.status_code == 201:
                    pr_data = response.json()
                    return pr_data.get("html_url")
                else:
                    logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error creating GitHub PR: {e}")
            return None
