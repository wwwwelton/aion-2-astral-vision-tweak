<#
.SYNOPSIS
    Compila astral_vision.py em AstralVision.exe autocontido (Nuitka onefile) e assina o resultado.
.DESCRIPTION
    Build local: assina com certificado de assinatura de código deste PC com carimbo de tempo da DigiCert.
    Build de release (-Release): assina com o certificado fixo das releases vindo dos Secrets do repositório
    (SIGNING_PFX_BASE64 e SIGNING_PFX_PASSWORD) e carimbo de tempo da DigiCert.
.PARAMETER CertThumbprint
    Usa outro certificado de assinatura de código em Cert:\CurrentUser\My.
.PARAMETER BuildDir
    Pasta de trabalho com o venv e a saída do Nuitka.
.PARAMETER Python
    Python usado para criar o venv do build.
.PARAMETER Version
    Versão gravada nas propriedades do .exe, com quatro números.
.PARAMETER Release
    Gera o build de release com o certificado fixo.
.PARAMETER Stage
    All (padrão), Compile ou Sign. A release usa etapas separadas no GitHub Actions.
.PARAMETER ReleaseThumbprint
    Thumbprint do certificado das releases.
#>
param(
    [string]$CertThumbprint,
    [string]$BuildDir = (Join-Path $env:LOCALAPPDATA "AstralVisionBuild"),
    [string]$Python = "python",
    [string]$Version = "1.0.0.0",
    [switch]$Release,
    [ValidateSet("All", "Compile", "Sign")]
    [string]$Stage = "All",
    [string]$ReleaseThumbprint = "C9DED1BED29518F899115B0DB13A5FE46A25DDEA"
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$ExeName = "AstralVision.exe"
$CertSubject = "CN=Astral Vision Installer - Local Build"
$TimestampServer = "http://timestamp.digicert.com"
$Venv = Join-Path $BuildDir "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Output = Join-Path $BuildDir "nuitka"

if ($Stage -ne "Sign") {
    # --- Ambiente de build isolado
    if (-not (Test-Path $VenvPython)) {
        & $Python -m venv $Venv
    }
    & $VenvPython -m pip install --quiet --disable-pip-version-check "nuitka==4.3.4" "zstandard"

    # --- Perfis e opções embutidos: o .exe funciona mesmo longe destas pastas.
    $Data = Join-Path $BuildDir "data\profiles"
    if (Test-Path $Data) {
        Remove-Item $Data -Recurse -Force
    }
    $null = New-Item -ItemType Directory $Data
    foreach ($Level in Get-ChildItem $PSScriptRoot -Directory | Where-Object Name -Match '^[1-5]-') {
        Copy-Item -LiteralPath $Level.FullName -Destination $Data -Recurse
    }
    foreach ($File in "Additions.txt", "FSR Frame Generation.txt", "FSR, DLSS, XESS.txt", "Reduce Stutters.txt", "VSync.txt", "Distance View Low.txt") {
        $FilePath = Join-Path $PSScriptRoot $File
        if (Test-Path $FilePath) {
            Copy-Item -LiteralPath $FilePath -Destination $Data
        }
    }
    Get-ChildItem $Data -Recurse -Force -Filter desktop.ini | Remove-Item -Force

    # --- Compilação
    & $VenvPython -m nuitka `
        --mode=onefile `
        --msvc=latest `
        --assume-yes-for-downloads `
        --windows-console-mode=force `
        --output-dir=$Output `
        --output-filename=$ExeName `
        --product-name="Astral Vision Installer" `
        --file-description="Instalador de perfis Astral Vision para AION 2 Global (Steam)" `
        --product-version=$Version `
        --file-version=$Version `
        "--include-data-dir=$Data=profiles" `
        (Join-Path $PSScriptRoot "astral_vision.py")
}

if ($Stage -eq "Compile") {
    return
}
# --- Certificado
if ($CertThumbprint) {
    $Cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprint"
} elseif ($Release) {
    if (-not $ReleaseThumbprint) {
        throw "Certificado das releases não configurado."
    }
    if (-not $env:SIGNING_PFX_BASE64 -or -not $env:SIGNING_PFX_PASSWORD) {
        throw "Faltam as variáveis de ambiente SIGNING_PFX_BASE64 e SIGNING_PFX_PASSWORD."
    }
    $Cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new(
        [Convert]::FromBase64String($env:SIGNING_PFX_BASE64), $env:SIGNING_PFX_PASSWORD.Trim())
    if ($Cert.Thumbprint -ne $ReleaseThumbprint) {
        throw "O certificado fornecido é $($Cert.Thumbprint), mas o esperado é $ReleaseThumbprint."
    }
} else {
    $Cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $CertSubject -and $_.NotAfter -gt (Get-Date) -and $_.HasPrivateKey } |
        Sort-Object NotAfter -Descending |
        Select-Object -First 1
    if (-not $Cert) {
        $Cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $CertSubject `
            -CertStoreLocation Cert:\CurrentUser\My -KeyAlgorithm RSA -KeyLength 3072 `
            -KeyExportPolicy NonExportable -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5)
    }
}

# --- Assinatura na pasta de build; só o arquivo final vai para o projeto
$Built = Join-Path $Output $ExeName
$Signature = Set-AuthenticodeSignature -FilePath $Built -Certificate $Cert -HashAlgorithm SHA256 `
    -TimestampServer $TimestampServer

# --- Conferência: 'UnknownError' é o esperado enquanto o autoassinado não estiver instalado
$Signature = Get-AuthenticodeSignature $Built
if ($Signature.SignerCertificate.Thumbprint -ne $Cert.Thumbprint -or
    $Signature.Status -in "NotSigned", "HashMismatch") {
    throw "Assinatura inválida: $($Signature.Status) - $($Signature.StatusMessage)"
}
if (-not $Signature.TimeStamperCertificate) {
    throw "O carimbo de tempo da DigiCert não foi aplicado."
}

$Exe = Join-Path $PSScriptRoot $ExeName
Copy-Item $Built $Exe -Force

[pscustomobject]@{
    Arquivo    = $Exe
    TamanhoMB  = [math]::Round((Get-Item $Exe).Length / 1MB, 1)
    Assinante  = $Cert.Subject
    Thumbprint = $Cert.Thumbprint
    Carimbo    = $Signature.TimeStamperCertificate.Subject
    Status     = $Signature.Status
    Mensagem   = $Signature.StatusMessage
} | Format-List
