"""
Git Status Tool for EVA-MCP Server.
Retrieves Git repository status including branch, commit, and modified files.
"""

import logging
from pathlib import Path
from typing import Any, Optional

from git import Repo, InvalidGitRepositoryError
from pydantic import BaseModel, Field

from eva_mcp.tools.base import BaseTool

logger = logging.getLogger(__name__)


# ============================================================================
# Input/Output Schemas
# ============================================================================

class GitStatusInput(BaseModel):
    """Input schema for Git status tool."""
    repo_dir: str = Field(
        description="Path to Git repository directory",
        examples=["/workspace/eva-mcp", "C:\\Users\\marco\\Documents\\_AI Dev\\EVA Suite\\eva-mcp"]
    )


class GitStatusOutput(BaseModel):
    """Output schema for Git status."""
    branch: str = Field(description="Current branch name")
    commit_hash: str = Field(description="Current commit SHA (short)")
    commit_message: str = Field(description="Current commit message")
    is_dirty: bool = Field(description="True if there are uncommitted changes")
    modified_files: list[str] = Field(description="List of modified file paths")
    untracked_files: list[str] = Field(description="List of untracked file paths")
    remote_url: Optional[str] = Field(default=None, description="Remote origin URL (if configured)")


# ============================================================================
# Git Status Tool
# ============================================================================

class GitStatusTool(BaseTool):
    """
    Get Git repository status.
    
    Retrieves branch, commit hash, modified files, and untracked files.
    Uses GitPython for repository operations.
    """
    
    name = "git_status"
    description = (
        "Get Git repository status including current branch, commit hash, "
        "commit message, modified files, and untracked files. "
        "Useful for understanding repository state before operations."
    )
    input_schema = GitStatusInput
    output_schema = GitStatusOutput
    required_roles = ["developer"]  # Protected tool - developers only
    
    def __init__(self):
        # No persistent connections needed for Git operations
        pass
    
    async def initialize(self) -> None:
        """
        No initialization required for Git operations.
        """
        logger.info("✓ Git status tool initialized")
    
    async def execute(
        self,
        args: GitStatusInput,
        user_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Get Git repository status.
        
        Args:
            args: Validated Git status parameters
            user_id: User executing query (for audit logging)
        
        Returns:
            Repository status with branch, commit, and file changes
        
        Raises:
            Exception: If path is not a Git repository or operation fails
        """
        logger.info(f"Getting Git status: repo_dir={args.repo_dir}, user={user_id}")
        
        # Validate repository path
        repo_path = Path(args.repo_dir)
        if not repo_path.exists():
            raise Exception(f"Repository path does not exist: {args.repo_dir}")
        
        if not repo_path.is_dir():
            raise Exception(f"Repository path is not a directory: {args.repo_dir}")
        
        try:
            # Open Git repository
            repo = Repo(str(repo_path))
            
            # Get current branch
            try:
                branch = repo.active_branch.name
            except Exception:
                # Detached HEAD state
                branch = "HEAD (detached)"
            
            # Get current commit
            commit = repo.head.commit
            commit_hash = commit.hexsha[:8]  # Short hash
            commit_message = commit.message.strip()
            
            # Check for uncommitted changes
            is_dirty = repo.is_dirty()
            
            # Get modified files (staged + unstaged)
            modified_files = []
            
            # Staged files
            for item in repo.index.diff("HEAD"):
                modified_files.append(item.a_path)
            
            # Unstaged files
            for item in repo.index.diff(None):
                if item.a_path not in modified_files:
                    modified_files.append(item.a_path)
            
            # Get untracked files
            untracked_files = repo.untracked_files
            
            # Get remote URL (if configured)
            remote_url = None
            try:
                if repo.remotes:
                    remote_url = repo.remotes.origin.url
            except Exception:
                # No remote configured
                pass
            
            result = {
                "branch": branch,
                "commit_hash": commit_hash,
                "commit_message": commit_message,
                "is_dirty": is_dirty,
                "modified_files": modified_files,
                "untracked_files": untracked_files,
                "remote_url": remote_url
            }
            
            logger.info(
                f"✓ Git status: branch={branch}, commit={commit_hash}, "
                f"modified={len(modified_files)}, untracked={len(untracked_files)}"
            )
            
            return result
        
        except InvalidGitRepositoryError:
            logger.error(f"✗ Not a Git repository: {args.repo_dir}")
            raise Exception(f"Not a Git repository: {args.repo_dir}")
        
        except Exception as e:
            logger.error(f"✗ Git status failed: {e}")
            raise Exception(f"Git status failed: {str(e)}")
    
    async def cleanup(self) -> None:
        """
        No cleanup required for Git operations.
        """
        pass
