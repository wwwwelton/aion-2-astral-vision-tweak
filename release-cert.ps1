<#
.SYNOPSIS
    Gera o certificado fixo das releases e guarda a chave privada nos Secrets do repositório no GitHub.
.DESCRIPTION
    Rode uma vez, e de novo só para trocar o certificado, quando ele expirar ou se a chave vazar.

    A chave só existe neste PC durante a execução. Depois, ela fica apenas nos Secrets, que não podem ser lidos
    de volta. O thumbprint é público: o script o grava no build.ps1, e essa alteração precisa ir num commit.

    Trocar o certificado muda o thumbprint: quem instalou o anterior precisa remover esse e instalar o novo.

    Exige PowerShell 7 e o GitHub CLI autenticado (gh auth login).
.PARAMETER Repository
    Repositório que recebe os Secrets.
.PARAMETER Years
    Validade do certificado, em anos.
#>
param(
    [string]$Repository = "wwwwelton/aion-2-astral-vision-tweak",
    [int]$Years = 5
)
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$Subject = "CN=Astral Vision Installer - Release"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI não encontrado. Instale com: winget install --id GitHub.cli -e"
}
& gh auth status | Out-Null

$Cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
    -CertStoreLocation Cert:\CurrentUser\My -KeyAlgorithm RSA -KeyLength 3072 `
    -KeyExportPolicy Exportable -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears($Years)
try {
    $Random = [byte[]]::new(32)
    [Security.Cryptography.RandomNumberGenerator]::Fill($Random)
    $Password = [Convert]::ToBase64String($Random)
    $Pfx = $Cert.Export([Security.Cryptography.X509Certificates.X509ContentType]::Pkcs12, $Password)

    # Pela entrada padrão, para os valores não aparecerem na linha de comando.
    [Convert]::ToBase64String($Pfx) | & gh secret set SIGNING_PFX_BASE64 --repo $Repository
    $Password | & gh secret set SIGNING_PFX_PASSWORD --repo $Repository
} finally {
    Remove-Item "Cert:\CurrentUser\My\$($Cert.Thumbprint)" -DeleteKey
    # O New-SelfSignedCertificate também deixa uma cópia pública nas autoridades intermediárias.
    Get-ChildItem Cert:\CurrentUser\CA | Where-Object Thumbprint -EQ $Cert.Thumbprint | Remove-Item
}

$BuildScript = Join-Path $PSScriptRoot "build.ps1"
$Text = [IO.File]::ReadAllText($BuildScript)
$Pinned = [regex]::Replace($Text, '(\[string\]\$ReleaseThumbprint = )"[^"]*"', "`$1`"$($Cert.Thumbprint)`"")
if ($Pinned -eq $Text -and $Text -notmatch [regex]::Escape($Cert.Thumbprint)) {
    throw "Não encontrei o parâmetro ReleaseThumbprint no build.ps1."
}
[IO.File]::WriteAllText($BuildScript, $Pinned, [Text.UTF8Encoding]::new($false))

[pscustomobject]@{
    Certificado = $Cert.Subject
    Thumbprint  = $Cert.Thumbprint
    Expira      = $Cert.NotAfter.ToString("yyyy-MM-dd")
    Secrets     = "SIGNING_PFX_BASE64, SIGNING_PFX_PASSWORD em $Repository"
    Falta       = "Fazer commit do build.ps1 com o novo thumbprint"
} | Format-List
