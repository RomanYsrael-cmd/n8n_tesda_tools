[CmdletBinding()]
param([string]$Server = 'romanserver-remote')

$ErrorActionPreference = 'Stop'
if ($Server -notmatch '^[a-zA-Z0-9_.@-]+$' -or $Server.StartsWith('-')) { throw 'Invalid SSH server name.' }
if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { throw 'OpenSSH client is required.' }
Write-Host 'Update the SaaS API on tools.romanlms.com' -ForegroundColor Cyan
Write-Host 'Only the platform LLM settings will change. Your key is sent over SSH without a local credentials file.'
$baseUrl = (Read-Host 'New API base URL (including /v1)').Trim().TrimEnd('/')
$parsed = $null
if (-not [Uri]::TryCreate($baseUrl, [UriKind]::Absolute, [ref]$parsed) -or $parsed.Scheme -notin @('http','https') -or $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment) { throw 'Enter an HTTP(S) base URL without credentials, a query, or a fragment.' }
$model = (Read-Host 'Model ID').Trim()
if (-not $model) { throw 'Model ID is required.' }
$secureKey = Read-Host 'New API key (leave empty to keep the saved key)' -AsSecureString
$pointer = [IntPtr]::Zero
try {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $payload = @{base_url=$baseUrl; model=$model; api_key=$key} | ConvertTo-Json -Compress
    # Only program code enters the command line. Credentials travel through stdin.
    $program = @'
import json, os, shutil, sys, time
from pathlib import Path
p = Path('/opt/tesda-saas/secrets/saas.json')
incoming = json.load(sys.stdin)
with p.open(encoding='utf-8-sig') as f:
    config = json.load(f)
llm = config.setdefault('platform_llm', {})
llm.update(base_url=incoming['base_url'], model=incoming['model'])
if incoming.get('api_key'):
    llm['api_key'] = incoming['api_key']
backup = p.with_name('saas.json.api-backup-' + str(time.time_ns()))
fd = os.open(str(backup), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'wb') as out, p.open('rb') as source:
    shutil.copyfileobj(source, out)
# Preserve the inode: Docker bind-mounts this individual file.
with p.open('w', encoding='utf-8') as out:
    json.dump(config, out, indent=2)
    out.flush()
    os.fsync(out.fileno())
os.chmod(p, 0o600)
print('API settings saved. Protected backup: ' + str(backup))
'@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($program))
    # Pass the encoded program as argv, avoiding nested double quotes that
    # Windows PowerShell 5.1 strips when invoking native executables.
    $remote = "sudo -n python3 -c 'import base64,sys;exec(base64.b64decode(sys.argv[1]))' $encoded"
    $payload | & ssh $Server $remote
    if ($LASTEXITCODE -ne 0) { throw 'Server update failed. Check SSH access and passwordless sudo.' }
}
finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $key = $null; $payload = $null; $secureKey.Dispose()
}

Write-Host 'The worker must restart to load the new API settings.' -ForegroundColor Yellow
Write-Host 'Wait until all generation jobs finish before restarting; restarting interrupts active jobs.'
$answer = Read-Host 'Type APPLY to restart only the TESDA worker now, or Enter to apply later'
if ($answer -ceq 'APPLY') {
    & ssh $Server 'sudo -n docker restart tesda-saas-worker'
    if ($LASTEXITCODE -ne 0) { throw 'Settings saved, but worker restart failed.' }
    Write-Host 'Worker restarted. New generation requests will use the updated API.' -ForegroundColor Green
} else {
    Write-Host 'Settings saved. When jobs finish, run:'
    Write-Host "ssh $Server sudo -n docker restart tesda-saas-worker"
}
