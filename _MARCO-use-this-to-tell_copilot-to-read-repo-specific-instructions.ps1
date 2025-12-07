# ============================================================================
# MARCO: Tell Copilot to Read Repo-Specific Instructions
# ============================================================================
# 
# PURPOSE:
# This script tells you the EXACT prompt to give GitHub Copilot when starting
# work in this repository. It ensures Copilot reads the .eva-memory.json and
# follows all repo-specific instructions, blockers, and specifications.
#
# HOW TO USE:
# 1. Run this script: .\_MARCO-use-this-to-tell_copilot-to-read-repo-specific-instructions.ps1
# 2. Copy the output text
# 3. Paste it as your FIRST message to GitHub Copilot in this workspace
#
# This prevents "vibe coding" - where Copilot starts working without
# understanding the repo context, blockers, or specifications.
# ============================================================================

$repoName = Split-Path -Leaf (Get-Location)

Write-Host "`n============================================================================" -ForegroundColor Cyan
Write-Host "COPY AND PASTE THIS TO GITHUB COPILOT:" -ForegroundColor Yellow
Write-Host "============================================================================`n" -ForegroundColor Cyan

Write-Host @"
Read .eva-memory.json and follow ALL instructions, blockers, and specifications before doing any work.

Specifically:
1. Read .eva-memory.json (context.blockers, memory.lessons, memory.patterns)
2. Check context.keyFiles and read those files
3. If there are blockers, STOP and address them first
4. Do NOT start coding without understanding the complete context
5. Follow the Three Concepts Pattern: Context Engineering, Workspace Management, Directory Mapping

Repository: $repoName
"@ -ForegroundColor Green

Write-Host "`n============================================================================" -ForegroundColor Cyan
Write-Host "After Copilot confirms it read the memory file, you can give your task." -ForegroundColor Gray
Write-Host "============================================================================`n" -ForegroundColor Cyan
