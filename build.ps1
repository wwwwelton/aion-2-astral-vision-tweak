<#
.SYNOPSIS
    Compila astral_vision.py em AstralVision.exe autocontido (Nuitka onefile) e assina o resultado.
.DESCRIPTION
    Cria, se preciso, um certificado autoassinado e assina o .exe com carimbo de tempo da DigiCert.
    A assinatura guarda o certificado público dentro do .exe. A chave privada fica em
    Cert:\CurrentUser\My, não exportável, e nunca entra no .exe.
.PARAMETER CertThumbprint
    Usa outro certificado de assinatura de código em Cert:\CurrentUser\My, como um emitido por uma CA.
.PARAMETER BuildDir
    Pasta de trabalho com o venv e a saída do Nuitka. Fica fora do projeto porque o projeto pode estar
    numa pasta sincronizada, e o venv tem milhares de arquivos.
.PARAMETER Python
    Python usado para criar o venv do build.
.PARAMETER Version
    Versão gravada nas propriedades do .exe, com quatro números.
#>
param(
    [string]$CertThumbprint,
    [string]$BuildDir = (Join-Path $env:LOCALAPPDATA "AstralVisionBuild"),
    [string]$Python = "python",
    [string]$Version = "1.0.0.0"
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$ExeName = "AstralVision.exe"
$CertSubject = "CN=Astral Vision Installer - Local Build"
$TimestampServer = "http://timestamp.digicert.com"
$Venv = Join-Path $BuildDir "venv"
$VenvPython = Join-Path $Venv "Scripts\python.exe"
$Output = Join-Path $BuildDir "nuitka"

# --- Ambiente de build isolado
if (-not (Test-Path $VenvPython)) {
    & $Python -m venv $Venv
}
& $VenvPython -m pip install --quiet --disable-pip-version-check "nuitka==4.3.4" "zstandard"

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
foreach ($File in "Additions.txt", "FSR Frame Generation.txt", "FSR, DLSS, XESS.txt", "Reduce Stutters.txt") {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $File) -Destination $Data
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

# --- Certificado
if ($CertThumbprint) {
    $Cert = Get-Item "Cert:\CurrentUser\My\$CertThumbprint"
} else {
    $Cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $CertSubject -and $_.NotAfter -gt (Get-Date) -and $_.HasPrivateKey } |
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
