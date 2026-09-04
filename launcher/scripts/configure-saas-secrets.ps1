[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $PSScriptRoot '..\..\.secrets\saas.json')
)

$ErrorActionPreference = 'Stop'

function Read-PlainValue {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [string]$Default = '',
        [switch]$Required
    )
    $suffix = if ($Default) { " [$Default]" } else { '' }
    do {
        $value = Read-Host "$Prompt$suffix"
        if ([string]::IsNullOrWhiteSpace($value)) { $value = $Default }
        if (-not $Required -or -not [string]::IsNullOrWhiteSpace($value)) { return $value.Trim() }
        Write-Warning 'This value is required.'
    } while ($true)
}

function Read-SecretValue {
    param(
        [Parameter(Mandatory)][string]$Prompt,
        [switch]$Required
    )
    do {
        $secure = Read-Host $Prompt -AsSecureString
        if ($secure.Length -gt 0) {
            $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
        }
        if (-not $Required) { return '' }
        Write-Warning 'This secret is required.'
    } while ($true)
}

function New-RandomSecret {
    param([int]$Bytes = 48)
    $buffer = [byte[]]::new($Bytes)
    [Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer)
}

Write-Host ''
Write-Host 'TESDA SaaS local secret configuration' -ForegroundColor Cyan
Write-Host 'Values entered as secrets are masked and are not printed.'
Write-Host 'The resulting file is ignored by Git. Do not upload or send it in chat.' -ForegroundColor Yellow
Write-Host ''

$firebaseServiceAccountPath = Read-PlainValue -Prompt 'Absolute path to the Firebase service-account JSON' -Required
if (-not (Test-Path -LiteralPath $firebaseServiceAccountPath -PathType Leaf)) {
    throw "Firebase service-account file not found: $firebaseServiceAccountPath"
}

$config = [ordered]@{
    version = 1
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    application = [ordered]@{
        public_base_url = Read-PlainValue -Prompt 'Public application URL' -Default 'https://tools.romanlms.com' -Required
        admin_email = Read-PlainValue -Prompt 'Initial SaaS administrator email' -Default 'admin@romanlms.com' -Required
        session_secret = New-RandomSecret
        data_encryption_key = New-RandomSecret -Bytes 32
    }
    firebase = [ordered]@{
        project_id = Read-PlainValue -Prompt 'Firebase project ID' -Required
        web_api_key = Read-SecretValue -Prompt 'Firebase web API key' -Required
        service_account_json_path = (Resolve-Path -LiteralPath $firebaseServiceAccountPath).Path
        web_push_vapid_public_key = Read-PlainValue -Prompt 'Firebase Web Push VAPID public key (optional)'
    }
    postgres = [ordered]@{
        database_url = Read-SecretValue -Prompt 'PostgreSQL URL, for example postgresql://user:password@host:5432/database' -Required
    }
    r2 = [ordered]@{
        account_id = Read-PlainValue -Prompt 'Cloudflare account ID' -Required
        bucket = Read-PlainValue -Prompt 'Private R2 bucket name' -Required
        access_key_id = Read-SecretValue -Prompt 'R2 access key ID' -Required
        secret_access_key = Read-SecretValue -Prompt 'R2 secret access key' -Required
    }
    paymongo = [ordered]@{
        public_key = Read-PlainValue -Prompt 'PayMongo public key (test key is recommended initially)' -Required
        secret_key = Read-SecretValue -Prompt 'PayMongo secret key' -Required
        webhook_secret = Read-SecretValue -Prompt 'PayMongo webhook signing secret (leave blank until the webhook exists)'
    }
    email = [ordered]@{
        smtp_host = Read-PlainValue -Prompt 'SMTP host' -Required
        smtp_port = [int](Read-PlainValue -Prompt 'SMTP port' -Default '465' -Required)
        smtp_username = Read-PlainValue -Prompt 'SMTP username' -Default 'admin@romanlms.com' -Required
        smtp_password = Read-SecretValue -Prompt 'SMTP password' -Required
        from_email = Read-PlainValue -Prompt 'Notification sender email' -Default 'admin@romanlms.com' -Required
    }
    platform_llm = [ordered]@{
        base_url = Read-PlainValue -Prompt 'Platform LLM OpenAI-compatible base URL (optional)'
        model = Read-PlainValue -Prompt 'Platform LLM model ID (optional)'
        api_key = Read-SecretValue -Prompt 'Platform LLM API key (optional)'
    }
}

$resolvedOutput = [IO.Path]::GetFullPath($OutputPath)
$outputDirectory = Split-Path -Parent $resolvedOutput
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
$config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resolvedOutput -Encoding utf8NoBOM

Write-Host ''
Write-Host "Saved SaaS configuration to: $resolvedOutput" -ForegroundColor Green
Write-Host 'Secrets were not printed. Keep this file private and include it in encrypted backups only.' -ForegroundColor Yellow
Write-Host 'You may rerun this script whenever a credential changes.'
