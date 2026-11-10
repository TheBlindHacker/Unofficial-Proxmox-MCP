# ==============================================================================
# Unofficial-Proxmox-MCP Windows & Cross-Platform PowerShell Installer
# ==============================================================================

[CmdletBinding()]
param (
    [ValidateSet("Local", "Docker")]
    [string]$Target = "Local"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   Unofficial-Proxmox-MCP PowerShell Installer 🚀          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$EnvFile = Join-Path $ScriptDir ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "`n[!] No .env file found. Configuring Proxmox connection:" -ForegroundColor Yellow
    $HostIp = Read-Host "Proxmox Host / IP [127.0.0.1]"
    if ([string]::IsNullOrWhiteSpace($HostIp)) { $HostIp = "127.0.0.1" }

    $Port = Read-Host "Proxmox Port [8006]"
    if ([string]::IsNullOrWhiteSpace($Port)) { $Port = "8006" }

    Write-Host "`n[Security Recommendation]" -ForegroundColor Yellow
    Write-Host "To create a dedicated, least-privilege user on Proxmox, run in PVE shell:" -ForegroundColor Gray
    Write-Host "  pveum role add MCPAgent --privs 'VM.Audit,VM.Console,VM.PowerMgmt,VM.Config.CPU,VM.Config.Memory,VM.Config.Disk,VM.Config.Network,VM.Config.Options,VM.Snapshot,VM.Snapshot.Rollback,VM.Clone,VM.Allocate,Datastore.Audit,Datastore.AllocateSpace,Sys.Audit,SDN.Audit'" -ForegroundColor DarkGray
    Write-Host "  pveum user add mcp-bot@pve -comment 'Dedicated AI Assistant User'" -ForegroundColor DarkGray
    Write-Host "  pveum acl modify / --users mcp-bot@pve --roles MCPAgent" -ForegroundColor DarkGray
    Write-Host "  pveum user token add mcp-bot@pve mcp-token -privsep 0`n" -ForegroundColor DarkGray

    $User = Read-Host "Proxmox API User [mcp-bot@pve!mcp-token]"
    if ([string]::IsNullOrWhiteSpace($User)) { $User = "mcp-bot@pve!mcp-token" }

    $Secret = Read-Host "Proxmox Token Secret UUID"

    $VerifySsl = Read-Host "Verify SSL? (true/false) [false]"
    if ([string]::IsNullOrWhiteSpace($VerifySsl)) { $VerifySsl = "false" }

    $Protected = Read-Host "Protected VM/LXC IDs [100,101]"
    if ([string]::IsNullOrWhiteSpace($Protected)) { $Protected = "100,101" }

    @"
PVE_HOST=$HostIp
PVE_PORT=$Port
PVE_USER=$User
PVE_TOKEN_SECRET=$Secret
PVE_VERIFY_SSL=$VerifySsl
PVE_PROTECTED_VMIDS=$Protected
MCP_TRANSPORT=stdio
MCP_HOST=0.0.0.0
MCP_PORT=8000
"@ | Out-File -FilePath $EnvFile -Encoding utf8

    Write-Host "[+] Saved $EnvFile" -ForegroundColor Green
}

if ($Target -eq "Local") {
    Write-Host "`n--- [Local Python Installation] ---" -ForegroundColor Cyan
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCmd) {
        Write-Error "Python is not installed or not in PATH."
    }

    $VenvDir = Join-Path $ScriptDir ".venv"
    if (-not (Test-Path $VenvDir)) {
        Write-Host "[+] Creating virtual environment in $VenvDir..." -ForegroundColor Cyan
        & python -m venv $VenvDir
    }

    $Pip = Join-Path $VenvDir "Scripts\pip.exe"
    $PveMcp = Join-Path $VenvDir "Scripts\unofficial-proxmox-mcp.exe"

    Write-Host "[+] Installing dependencies..." -ForegroundColor Cyan
    & $Pip install --upgrade pip
    & $Pip install -e $ScriptDir

    Write-Host "`n[+] Running connectivity pre-flight check..." -ForegroundColor Green
    & $PveMcp --check

    Write-Host "`n============================================================" -ForegroundColor Green
    Write-Host "Claude Desktop Configuration Snippet:" -ForegroundColor Green
    Write-Host @"
{
  "mcpServers": {
    "proxmox": {
      "command": "$($PveMcp.Replace('\', '\\'))",
      "args": ["--transport", "stdio"]
    }
  }
}
"@ -ForegroundColor Yellow
    Write-Host "============================================================" -ForegroundColor Green
} elseif ($Target -eq "Docker") {
    Write-Host "`n--- [Docker Deployment] ---" -ForegroundColor Cyan
    Push-Location $ScriptDir
    docker compose down 2>$null
    docker compose up -d --build
    Pop-Location
    Write-Host "[+] Docker container is up and running on port 8000 (SSE transport)." -ForegroundColor Green
}
