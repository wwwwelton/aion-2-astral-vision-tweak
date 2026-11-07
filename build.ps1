<#
.SYNOPSIS
    Compila o programa em AstralVision.exe autocontido (Nuitka onefile) e assina o resultado.
.DESCRIPTION
    Build local: traz o serviço de energia e assina sempre com o mesmo certificado autoassinado deste PC,
    guardado em Cert:\CurrentUser\My com chave não exportável. Ele só é criado se ainda não existir.

    Build de release (-Release): não traz o serviço, porque o Microsoft Defender bloqueia o .exe quando ele roda
    sem janela e grava a inicialização automática. Assina com o certificado fixo das releases, cuja chave vem dos
    Secrets do repositório (ver release-cert.ps1).

    Nos dois casos, a assinatura guarda só o certificado público dentro do .exe e leva carimbo de tempo da DigiCert.
.PARAMETER CertThumbprint
    Usa outro certificado de assinatura de código em Cert:\CurrentUser\My, como um emitido por uma CA.
.PARAMETER BuildDir
    Pasta de trabalho com o venv e a saída do Nuitka. Fica fora do projeto porque o projeto pode estar
    numa pasta sincronizada, e o venv tem milhares de arquivos.
.PARAMETER Python
    Python usado para criar o venv do build.
.PARAMETER Version
    Versão gravada nas propriedades do .exe, com quatro números.
.PARAMETER Release
    Gera o build de release, sem o serviço de energia.
.PARAMETER Stage
    All (padrão), Compile ou Sign. A release usa etapas separadas, para o compilador e as dependências dele
    rodarem sem acesso à chave.
.PARAMETER ReleaseThumbprint
    Thumbprint do certificado das releases, gravado aqui pelo release-cert.ps1. A assinatura falha se o
    certificado dos Secrets for outro.
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
# Auto-elevação via UAC quando executado localmente sem privilégios de Administrador
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin -and -not $env:GITHUB_ACTIONS) {
    Write-Host "Solicitando permissão de Administrador (UAC)..."
    $ForwardArgs = @("-ExecutionPolicy", "Bypass", "-NoProfile", "-File", "`"$PSCommandPath`"")
    foreach ($k in $PSBoundParameters.Keys) {
        $v = $PSBoundParameters[$k]
        if ($v -is [switch]) {
            if ($v.IsPresent) { $ForwardArgs += "-$k" }
        } else {
            $ForwardArgs += "-$k"
            $ForwardArgs += "`"$v`""
        }
    }
    $Proc = Start-Process powershell.exe -WorkingDirectory $PSScriptRoot -ArgumentList $ForwardArgs -Verb RunAs -PassThru -Wait
    if ($Proc -and $null -ne $Proc.ExitCode -and $Proc.ExitCode -ge 0) {
        exit $Proc.ExitCode
    }
    exit 0
}

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
    & $VenvPython -m pip install --quiet --disable-pip-version-check "nuitka==4.3.4" "zstandard" `
        -r (Join-Path $PSScriptRoot "requirements.txt")

    # --- Perfis e opções embutidos: o .exe funciona mesmo longe destas pastas.
    # Passam por uma pasta intermediária porque o Nuitka descarta, sem erro, arquivos com vírgula no nome
    # informados na linha de comando, como "FSR, DLSS, XESS.txt".
    $Data = Join-Path $BuildDir "data\profiles"
    if (Test-Path $Data) {
        Remove-Item $Data -Recurse -Force
    }
    $null = New-Item -ItemType Directory $Data
    foreach ($Level in Get-ChildItem $PSScriptRoot -Directory | Where-Object Name -Match '^[1-5]-') {
        Copy-Item -LiteralPath $Level.FullName -Destination $Data -Recurse
    }
    foreach ($File in "Additions.txt", "FSR Frame Generation.txt", "FSR, DLSS, XESS.txt", "Reduce Stutters.txt", "VSync.txt", "Distance View Low.txt") {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $File) -Destination $Data
    }
    Get-ChildItem $Data -Recurse -Force -Filter desktop.ini | Remove-Item -Force
    # PresentMon oficial embutido no onefile; o hash impede executar um download substituído.
    $PresentMon = Join-Path $BuildDir "PresentMon-2.3.1-x64.exe"
    if (-not (Test-Path $PresentMon)) {
        Invoke-WebRequest "https://github.com/GameTechDev/PresentMon/releases/download/v2.3.1/PresentMon-2.3.1-x64.exe" -OutFile $PresentMon
    }
    $ActualHash = if (Get-Command Get-FileHash -ErrorAction SilentlyContinue) {
        (Get-FileHash $PresentMon -Algorithm SHA256).Hash
    } else {
        [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash([System.IO.File]::ReadAllBytes($PresentMon))).Replace("-", "")
    }
    if ($ActualHash -ne "364E5D98D4D134BD54DD25C22ED2CA2F4883F8BC3ED6502BEE0C151E3436D30C") {
        throw "PresentMon não corresponde ao binário oficial esperado."
    }


    # --- Compilação (executável portátil autocontido, sem instalador)
    $ModeArgs = @("--windows-console-mode=force")
    $CaptureDll = Join-Path $BuildDir "presentmon_capture.dll"
    if (Test-Path $CaptureDll) {
        $ModeArgs += "--include-data-file=$CaptureDll=presentmon_capture.bin"
    }
    $Icon = Join-Path $PSScriptRoot "astral_vision.ico"
    if (Test-Path $Icon) {
        $ModeArgs += "--windows-icon-from-ico=$Icon"
        $ModeArgs += "--include-data-file=$Icon=astral_vision.ico"
    }
    # O Textual e o Rich carregam widgets e tabelas por nome, o que o Nuitka não enxerga sozinho.
    & $VenvPython -m nuitka `
        --mode=onefile `
        --msvc=latest `
        --assume-yes-for-downloads `
        @ModeArgs `
        --include-package=textual.widgets `
        --include-package=rich._unicode_data `
        --include-distribution-metadata=textual `
        --nofollow-import-to=textual.demo `
        --nofollow-import-to=textual.cli `
        --output-dir=$Output `
        --output-filename=$ExeName `
        --product-name="Astral Vision" `
        --file-description="Astral Vision Tweak para AION 2 Global (Steam)" `
        --product-version=$Version `
        --file-version=$Version `
        "--include-data-dir=$Data=profiles" `
        "--include-data-file=$PresentMon=PresentMon.exe" `
        "--include-data-file=$PSScriptRoot\README.md=README.md" `
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
        throw "Certificado das releases não configurado: rode o release-cert.ps1."
    }
    if (-not $env:SIGNING_PFX_BASE64 -or -not $env:SIGNING_PFX_PASSWORD) {
        throw "Faltam os Secrets SIGNING_PFX_BASE64 e SIGNING_PFX_PASSWORD: rode o release-cert.ps1."
    }
    $Cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new(
        [Convert]::FromBase64String($env:SIGNING_PFX_BASE64), $env:SIGNING_PFX_PASSWORD.Trim())
    if ($Cert.Thumbprint -ne $ReleaseThumbprint) {
        throw "O certificado dos Secrets é $($Cert.Thumbprint), mas o esperado é $ReleaseThumbprint."
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
