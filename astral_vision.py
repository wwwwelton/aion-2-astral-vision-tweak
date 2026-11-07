#!/usr/bin/env python3
"""Astral Vision - instalador de perfis para o Engine.ini do AION 2 Global (Steam).

Mescla um perfil (pastas 1- a 5-) e as opções extras (.txt) no Engine.ini do jogo,
mantendo um backup original ao lado do arquivo. Usa apenas a biblioteca padrão.

Uso:  AstralVision.exe [--ini CAMINHO\\Engine.ini] [--profiles PASTA]
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import msvcrt
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

APP = "Astral Vision"
INI_NAME = "Engine.ini"
ORIGINAL_BAK = "Engine.ini.original.bak"
STATE_NAME = "Engine.ini.astralvision.json"
BACKUP_PREFIX = "Engine.ini.backup-"
EMBEDDED_DIR = "profiles"  # perfis incluídos no .exe pelo build.ps1
STEAM_LAUNCH = "-xgeshadercompile -nothreadtimeout"
GAME_PROCESSES = {"aion2.exe", "aion.exe"}  # Steam: Aion2\Binaries\Win64\AION2.exe
RENDERER_SECTION = "/Script/Engine.RendererSettings"
MAIN_SECTIONS = (
    "/Script/Engine.Engine",
    "ConsoleVariables",
    RENDERER_SECTION,
    "SystemSettings",
)
# Gravadas pelo jogo ao escolher o upscaler: seguem o arquivo atual, não o backup original.
UPSCALER_KEYS = {"r.ngx.dlss.enable", "r.fidelityfx.fsr.enabled"}
DLSS_ON_RE = re.compile(r"(?im)^r\.ngx\.dlss\.enable=(1|true)\s*$")
# O jogo traz o plugin AMD FSR Upscaling (FSR 4), que substitui o de FSR 3 e usa r.FidelityFX.FSR.*.
# Só ganham o nome novo as chaves do mod que constam no guia atual do plugin (gpuopen.com/learn/ue-fsr4).
FSR3_SECTION = "/Script/FFXFSR3Settings.FFXFSR3Settings"
FSR_CURRENT_KEYS = {
    "forcevertexdeformationoutputsvelocity",
    "reactivehistorytranslucencylumabias",
    "reactivemaskpredoftranslucencyscale",
    "reactivemasktranslucencylumabias",
    "reactivehistorytranslucencybias",
    "reactivemasktranslucencybias",
    "reactivemaskroughnessscale",
    "usessrexperimentaldenoiser",
    "adjustmipbias",
    "historyformat",
    "autoexposure",
    "qualitymode",
    "sharpness",
    "dedither",
}
LEVEL_RE = re.compile(r"^[1-5]-")
LEVEL_INFO = {
    "1": "Denoisers e SSR desativados",
    "2": "Sombras e reflexos estáveis",
    "3": "Mais sombras e AO melhor; Astral Shadows e nuvens opcionais",
    "4": "Nanite contra pop-in em GPUs modernas; pesa em placas antigas",
    "5": "Lumen e Nanite com otimizações máximas de nitidez",
}
VARIANT_INFO = {
    "taa": "Temporal AA otimizado, efeitos temporais minimizados",
    "tsr": "Temporal Super Resolution, nitidez máxima",
    "astral shadows": "Sombras nítidas exclusivas do Astral Vision",
    "default shadows": "Sombras padrão (use se ficarem pixeladas)",
    "astral clouds": "Nuvens ocultas do AION 2, mais FPS em placas antigas",
    "volumetric clouds": "Nuvens padrão do jogo",
    "lumen on": "Lumen ligado",
    "lumen off": "Lumen desligado",
}
# (tecla, trecho do subtítulo em Additions.txt, rótulo)
ADDITIONS = (
    ("A", "lighting", "Additions: melhorar iluminação"),
    ("E", "skill", "Additions: remover efeitos de skills"),
    ("L", "latency", "Additions: reduzir latência"),
)
# (tecla, arquivo, rótulo)
OPTION_FILES = (
    ("G", "FSR Frame Generation.txt", "FSR Frame Generation"),
    ("F", "FSR, DLSS, XESS.txt", "FSR / DLSS / XeSS otimizados"),
    ("S", "Reduce Stutters.txt", "Reduce Stutters"),
)


# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
def default_ini() -> Path:
    """Engine.ini do AION 2 Global na Steam (usa Saved_Steam, não Saved)."""
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "AION2" / "Saved_Steam" / "Config" / "Windows" / INI_NAME


def app_dir() -> Path:
    """Pasta do .exe: no onefile do Nuitka, argv[0] aponta o binário real, não o temp."""
    return Path(sys.argv[0]).resolve().parent


def embedded_root() -> Path:
    return Path(__file__).resolve().parent / EMBEDDED_DIR


def level_dirs(root: Path) -> list[Path]:
    return sorted(d for d in root.iterdir() if d.is_dir() and LEVEL_RE.match(d.name))


def find_profiles_root(explicit: str | None) -> Path | None:
    """Perfis ao lado do programa têm prioridade; os embutidos no .exe são o último recurso."""
    candidates = [Path(explicit)] if explicit else [app_dir(), Path.cwd(), embedded_root()]
    return next((c for c in candidates if c.is_dir() and level_dirs(c)), None)


# --------------------------------------------------------------------------- #
# Modelo de INI (preserva a ordem e o texto das linhas)
# --------------------------------------------------------------------------- #
HEADER_RE = re.compile(r"^\s*\[(.+?)\]\s*$")


@dataclass
class Section:
    name: str | None
    lines: list[str] = field(default_factory=list)


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # a Unreal grava UTF-16 quando há texto não ASCII
        return data.decode("utf-16")
    return data.decode("utf-8-sig", errors="replace")


def find_section(sections: list[Section], name: str) -> Section:
    for section in sections:
        if section.name and section.name.lower() == name.lower():
            return section
    section = Section(name)
    sections.append(section)
    return section


def parse_ini(text: str) -> list[Section]:
    sections = [Section(None)]
    current = sections[0]
    for raw in text.splitlines():
        header = HEADER_RE.match(raw)
        if header:
            current = find_section(sections, header.group(1).strip())
        else:
            current.lines.append(raw.rstrip())
    return sections


def render_ini(sections: list[Section]) -> str:
    out: list[str] = []
    for section in sections:
        body = list(section.lines)
        while body and not body[-1].strip():
            body.pop()
        if section.name is None and not body:
            continue
        if section.name is not None:
            out.append(f"[{section.name}]")
        out.extend(body)
        out.append("")
    return "\r\n".join(out).rstrip("\r\n") + "\r\n"


def line_key(line: str) -> str | None:
    """Chave substituível de 'chave=valor'. Operadores de lista (+ - . !) acumulam, não substituem."""
    text = line.strip()
    if not text or text[0] in ";#+-.!" or "=" not in text:
        return None
    return text.split("=", 1)[0].strip().lower()


def overlay(section: Section, lines: list[str]) -> None:
    """As chaves definidas em `lines` substituem as da seção; todo o resto é mantido."""
    keys = {key for key in map(line_key, lines) if key}
    kept = [line for line in section.lines if line_key(line) not in keys]
    while kept and not kept[-1].strip():
        kept.pop()
    existing = {line.strip() for line in kept}
    section.lines = kept + [
        line for line in lines if line.strip() and (line_key(line) or line.strip() not in existing)
    ]


# --------------------------------------------------------------------------- #
# Opções extras (lidas dos .txt)
# --------------------------------------------------------------------------- #
@dataclass
class Option:
    key: str
    label: str
    main_lines: list[str] = field(default_factory=list)  # vão nos 4 colchetes principais
    extra: dict[str, list[str]] = field(default_factory=dict)  # vão em seções próprias


SETTING_RE = re.compile(r"^[A-Za-z+\-!.][^=\s]*=")


def parse_option_file(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    main: list[str] = []
    extra: dict[str, list[str]] = {}
    current: str | None = None
    in_main = True
    for raw in read_text(path).splitlines():
        line = raw.strip()
        header = HEADER_RE.match(line)
        if re.match(r"^-\s*Copy to engine\.ini \(NOT under", line, re.I):
            in_main, current = False, None
        elif header:
            in_main, current = False, header.group(1).strip()
            extra.setdefault(current, [])
        elif SETTING_RE.match(line):
            if in_main:
                main.append(line)
            elif current:
                extra[current].append(line)
    return main, extra


def parse_additions(path: Path) -> dict[str, list[str]]:
    """Additions.txt tem blocos no formato '-Subtítulo:' seguidos de linhas chave=valor."""
    groups: dict[str, list[str]] = {}
    current: str | None = None
    for raw in read_text(path).splitlines():
        line = raw.strip()
        title = re.match(r"^-\s*(.+?):\s*$", line)
        if title:
            current = title.group(1).lower()
            groups[current] = []
        elif current and SETTING_RE.match(line):
            groups[current].append(line)
    return groups


def current_fsr_lines(extra: dict[str, list[str]]) -> list[str]:
    """Repete nos colchetes principais as chaves de FSR 3 do mod, com os nomes do plugin atual."""
    lines = []
    for line in extra.get(FSR3_SECTION, []):
        key = line_key(line) or ""
        if key == "r.fidelityfx.fi.allowasyncworkloads":
            lines.append(line)
        elif key.startswith("r.fidelityfx.fsr3.") and key.rpartition(".")[2] in FSR_CURRENT_KEYS:
            lines.append(re.sub(r"(?i)\.FSR3\.", ".FSR.", line, count=1))
    return lines


def load_options(root: Path) -> tuple[list[Option], list[str]]:
    options: list[Option] = []
    problems: list[str] = []
    additions = root / "Additions.txt"
    if additions.is_file():
        groups = parse_additions(additions)
        for key, fragment, label in ADDITIONS:
            lines = next((v for title, v in groups.items() if fragment in title and v), None)
            if lines:
                options.append(Option(key, label, lines))
            else:
                problems.append(f"Bloco '{fragment}' não encontrado em Additions.txt")
    else:
        problems.append("Arquivo ausente: Additions.txt")
    for key, filename, label in OPTION_FILES:
        path = root / filename
        if path.is_file():
            main, extra = parse_option_file(path)
            options.append(Option(key, label, main + current_fsr_lines(extra), extra))
        else:
            problems.append(f"Arquivo ausente: {filename}")
    return options, problems


def apply_option(sections: list[Section], option: Option) -> None:
    if option.main_lines:
        for name in MAIN_SECTIONS:
            overlay(find_section(sections, name), option.main_lines)
    for name, lines in option.extra.items():
        overlay(find_section(sections, name), lines)


# --------------------------------------------------------------------------- #
# Perfis
# --------------------------------------------------------------------------- #
def find_engine_ini(folder: Path) -> Path | None:
    return next(
        (f for f in folder.iterdir() if f.is_file() and f.name.lower() == INI_NAME.lower()), None
    )


def subdirs(folder: Path) -> list[Path]:
    return sorted((d for d in folder.iterdir() if d.is_dir()), key=lambda d: d.name.lower())


def pretty_profile(rel: str | None) -> str:
    return rel.replace("/", " / ") if rel else "nenhum"


# --------------------------------------------------------------------------- #
# Instalação, backup e estado
# --------------------------------------------------------------------------- #
def sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def replace_with_retry(source: Path, dest: Path, attempts: int = 25) -> None:
    """Antivírus e sincronizadores, como o Google Drive, seguram arquivos por instantes."""
    for attempt in range(attempts):
        try:
            os.replace(source, dest)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.2)


def replace_file(path: Path, data: bytes) -> None:
    """Escrita atômica que mantém o atributo somente-leitura, se o arquivo já o tinha."""
    was_readonly = path.exists() and not os.access(path, os.W_OK)
    if was_readonly:
        os.chmod(path, stat.S_IWRITE)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(data)
        replace_with_retry(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
        if was_readonly:
            os.chmod(path, stat.S_IREAD)


def copy_writable(source: Path, dest: Path) -> None:
    """Backups nunca herdam o somente-leitura do Engine.ini."""
    shutil.copy2(source, dest)
    os.chmod(dest, stat.S_IWRITE)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def running_game_process() -> str | None:
    """Nome do processo do jogo em execução. Se não der para verificar, levanta OSError."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    entry_ptr = ctypes.POINTER(PROCESSENTRY32W)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, entry_ptr)
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, entry_ptr)
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS
    if snapshot in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.lower() in GAME_PROCESSES:
                return entry.szExeFile
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return None


class GameRunning(Exception):
    """O jogo está aberto: o Engine.ini não pode ser alterado."""


def require_game_closed() -> None:
    name = running_game_process()
    if name:
        raise GameRunning(f"Bloqueado: feche o jogo ({name}) antes de alterar o Engine.ini.")


class Manager:
    def __init__(self, ini: Path, root: Path):
        self.ini = ini
        self.root = root
        self.dir = ini.parent
        self.original = self.dir / ORIGINAL_BAK
        self.state_path = self.dir / STATE_NAME
        self.options, self.problems = load_options(root)
        self.state: dict = {
            "profile": None,
            "options": [],
            "last_sha": None,
            "upscaler": [],
            "original_missing": False,
            "original_readonly": False,
            "sign_asked": None,  # hash do .exe já perguntado: cada versão publicada tem certificado próprio
        }
        if self.state_path.is_file():
            try:
                self.state.update(json.loads(self.state_path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                self.problems.append(f"Estado ilegível, ignorado: {STATE_NAME}")

    def save_state(self) -> None:
        replace_file(self.state_path, json.dumps(self.state, indent=2, ensure_ascii=False).encode("utf-8"))

    @property
    def readonly(self) -> bool:
        return self.ini.exists() and not os.access(self.ini, os.W_OK)

    @property
    def installed(self) -> bool:
        return bool(self.state["profile"] or self.state["options"])

    @property
    def changed_outside(self) -> bool:
        """O Engine.ini não é mais o que o programa gravou (o jogo ou o usuário o alterou)."""
        return self.installed and sha256(self.ini) != self.state["last_sha"]

    # -- backups
    def ensure_original(self) -> str | None:
        """Primeira execução: cria o backup original ao lado do Engine.ini."""
        if self.original.exists():
            return None
        if self.ini.is_file():
            self.state["original_readonly"] = self.readonly
            copy_writable(self.ini, self.original)
            message = f"Backup original criado: {self.original.name}"
        else:
            self.original.write_bytes(b"")
            self.state["original_missing"] = True
            message = "Engine.ini não existia: o backup original foi criado vazio."
        self.save_state()
        return message

    def backup_now(self, tag: str = "") -> Path | None:
        if not self.ini.is_file():
            return None
        dest = self.dir / f"{BACKUP_PREFIX}{datetime.now():%Y%m%d-%H%M%S}{tag}"
        copy_writable(self.ini, dest)
        return dest

    def list_backups(self) -> list[Path]:
        backups = [self.original] if self.original.is_file() else []
        return backups + sorted(self.dir.glob(BACKUP_PREFIX + "*"), reverse=True)

    def keep_outside_changes(self) -> None:
        """Se o arquivo mudou fora do programa, guarda uma cópia antes de sobrescrever."""
        current = sha256(self.ini)
        if current and current not in (self.state["last_sha"], sha256(self.original)):
            self.backup_now("-auto")

    def capture_upscaler(self) -> None:
        section = find_section(parse_ini(read_text(self.ini)), RENDERER_SECTION)
        self.state["upscaler"] = [line for line in section.lines if line_key(line) in UPSCALER_KEYS]

    # -- ações
    def toggle_readonly(self) -> str:
        require_game_closed()
        if not self.ini.is_file():
            return "Engine.ini não existe: nada para marcar."
        if self.readonly:
            os.chmod(self.ini, stat.S_IWRITE)
            return "Somente leitura DESMARCADO: o jogo pode gravar no Engine.ini."
        os.chmod(self.ini, stat.S_IREAD)
        return "Somente leitura MARCADO: o jogo não consegue regravar o Engine.ini."

    def build(self, profile: str | None, option_keys: list[str]) -> str:
        """Sempre recalcula: original + upscaler escolhido no jogo + perfil + opções (ordem do menu)."""
        sections = parse_ini(read_text(self.original))
        if self.state["upscaler"]:
            overlay(find_section(sections, RENDERER_SECTION), self.state["upscaler"])
        if profile:
            folder = self.root / profile
            source = find_engine_ini(folder) if folder.is_dir() else None
            if not source:
                raise FileNotFoundError(f"Perfil não encontrado: {profile}")
            for part in parse_ini(read_text(source)):
                if part.name:
                    overlay(find_section(sections, part.name), part.lines)
        for option in self.options:
            if option.key in option_keys:
                apply_option(sections, option)
        return render_ini(sections)

    def apply(self, profile: str | None, option_keys: list[str]) -> str:
        if not profile and not option_keys:
            return self.uninstall()
        require_game_closed()
        self.ensure_original()
        rewritten = self.ini.is_file() and sha256(self.ini) != self.state["last_sha"]
        if rewritten and "G" not in self.state["options"]:
            self.capture_upscaler()  # o jogo regravou o arquivo: vale a escolha atual, não a do backup
        text = self.build(profile, option_keys)
        self.keep_outside_changes()
        replace_file(self.ini, text.encode("utf-8"))
        previous = self.state["profile"]
        self.state.update(profile=profile, options=option_keys, last_sha=sha256(self.ini))
        self.save_state()
        message = f"Instalado. Perfil: {pretty_profile(profile)} | Opções extras: {len(option_keys)}"
        if previous and profile and previous != profile:
            message += f"\nSubstituiu: {pretty_profile(previous)}"
        if "G" in option_keys and DLSS_ON_RE.search(text):
            message += ("\nAtenção: o Engine.ini tem DLSS ligado e o Frame Generation liga o FSR. "
                        "Escolha FSR como upscaler no jogo.")
        return message

    def uninstall(self) -> str:
        require_game_closed()
        self.ensure_original()
        self.keep_outside_changes()
        if self.state["original_missing"]:
            if self.ini.exists():
                os.chmod(self.ini, stat.S_IWRITE)
                self.ini.unlink()
        else:
            replace_file(self.ini, self.original.read_bytes())
            os.chmod(self.ini, stat.S_IREAD if self.state["original_readonly"] else stat.S_IWRITE)
        self.state.update(profile=None, options=[], upscaler=[], last_sha=sha256(self.ini))
        self.save_state()
        return "Desinstalado: Engine.ini original restaurado."

    def restore(self, backup: Path) -> str:
        if backup == self.original:
            return self.uninstall()
        require_game_closed()
        self.ensure_original()
        self.keep_outside_changes()
        replace_file(self.ini, backup.read_bytes())
        self.capture_upscaler()
        self.state.update(profile=None, options=[], last_sha=sha256(self.ini))
        self.save_state()
        return f"Restaurado de {backup.name}. Nenhum perfil marcado como instalado."


# --------------------------------------------------------------------------- #
# Assinatura do .exe
# --------------------------------------------------------------------------- #
# O build.ps1 assina com o certificado autoassinado fixo e carimbo de tempo da DigiCert. A assinatura guarda
# o certificado público dentro do .exe; a chave privada fica protegida nos Secrets do repositório no GitHub.
TRUST_STORE = "Root"
EMBEDDED_CERT_THUMBPRINT = "C9DED1BED29518F899115B0DB13A5FE46A25DDEA"
EMBEDDED_CERT_B64 = (
    "MIIEFDCCAnygAwIBAgIQJveyHLAf/ZRPwt32dKC7nTANBgkqhkiG9w0BAQsFADAi"
    "MSAwHgYDVQQDDBdBc3RyYWwgVmlzaW9uIC0gUmVsZWFzZTAeFw0yNjExMDcwMDUx"
    "NDRaFw0zMTExMDcwMTAxNDRaMCIxIDAeBgNVBAMMF0FzdHJhbCBWaXNpb24gLSBS"
    "ZWxlYXNlMIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAqMmrZOFHj2Na"
    "HM5RLONgzZe88/P+YOPnqHtg6kkOCiPAofwVrvvsGwZ6PEowpb/YNYddRtG2lt9+"
    "7EaiVSYmXzEHy/7XjnMadk9REpd9vFizbFo8FRVvWLrjfoNAh4eJ/iJtAmMH0u19"
    "daxBPUxWZrGzp26FPxbSHpWTj+/pOiC+bu4t94bJ/lMiRqIvP0cskka7ngbc7LOQ"
    "QxQtIzkWn2f0ljIWcVi3PA7URkOlkLU0JFDYCCHGCq8MAPJoT1oPDd9ae9Cv0SM1"
    "7THf/p72xoPycNUaB2LYlul86+ijN6srNpEWooiMRvJFarABQkeccwE8+HwqojXm"
    "I4TVVayk6Y3Z2tsEqN44UeIlZ6hMrUHiOpNoXTQU+RQ1iVXMIt17vF6rFXr+nt4c"
    "7+sR/eOQmKPpuRb9PYMP6ew3IMZVmMl/R4jg0LUSUvA8cYzVJSgO6GV29TUR9cZL"
    "y6qh1splvFTDSGwQ9vtY5IjEpcxeb41NWv20eZdADBrVgt1mpDexAgMBAAGjRjBE"
    "MA4GA1UdDwEB/wQEAwIHgDATBgNVHSUEDDAKBggrBgEFBQcDAzAdBgNVHQ4EFgQU"
    "RNYcYFFSeFA9SDdhBOWpcaI8BiswDQYJKoZIhvcNAQELBQADggGBAHETxLas9Nqp"
    "w0qvuqIej0Wu30ChuL1JZczqnQvVJZx+bC5Da0TKGNXt04xwir9yejoEINUkQuSt"
    "pWVMSf8QG0qc1Ux5YK/PHIf1GWMc8dCR0cKvz2Jwam5uYZILnwAmwQC4DOrr+DTn"
    "bMuC7aLApjPJh6bFF5hrFVawVapcDRD7wVFgQX485SXibCkh6Hf4p/UVtH/XLf1W"
    "9rundtnSaPqhv7cxPzV2kcnxjXDcJDG3KOoS2eA5Dg0+tmCmD4bsWygtgdrz8gNP"
    "fShl6b2a/TY2FRtfpb1ZSkg/yO5McZPsUMVJ0d9IDpxeOSqjbnqgdCldIggGh4y0"
    "2rbwBDNed+lCwNizCdsZqVxJhL8WHorzucHLHB/A8aDV7WnHMXpUeOyni8Jvwvdg"
    "l8aW15+Abi1hIRtAAu5nK9EFmcV73xPmQu6M6bSiSEJaoyi6r6UXT3dvvJT5fK8x"
    "3WyxLL7NweC62LtEBx5PD0hGdD02eei1jXkY+XLjlSHdF58nDLGwXg=="
)
READ_SIGNATURE_SCRIPT = r"""
if ($env:ASTRAL_EXE -and (Test-Path -LiteralPath $env:ASTRAL_EXE)) {
    $sig = Get-AuthenticodeSignature -LiteralPath $env:ASTRAL_EXE
    '{0}|{1}|{2}' -f $sig.Status, $sig.SignerCertificate.Subject, [bool]$sig.TimeStamperCertificate
} else {
    $found = Get-ChildItem Cert:\CurrentUser\Root | Where-Object Thumbprint -EQ $env:ASTRAL_THUMBPRINT | Select-Object -First 1
    if ($found) {
        'Valid|CN=Astral Vision - Release|True'
    } else {
        'UnknownError|CN=Astral Vision - Release|True'
    }
}
"""
CHANGE_TRUST_SCRIPT = r"""
$cert = $null
if ($env:ASTRAL_EXE -and (Test-Path -LiteralPath $env:ASTRAL_EXE)) {
    $cert = (Get-AuthenticodeSignature -LiteralPath $env:ASTRAL_EXE).SignerCertificate
}
if (-not $cert -and $env:ASTRAL_CERT_B64) {
    $cert = [Security.Cryptography.X509Certificates.X509Certificate2]::new([Convert]::FromBase64String($env:ASTRAL_CERT_B64))
}
if (-not $cert) { throw 'Nenhum certificado disponível.' }
$store = [Security.Cryptography.X509Certificates.X509Store]::new($env:ASTRAL_STORE, 'CurrentUser')
$store.Open('ReadWrite')
try {
    if ($env:ASTRAL_ACTION -eq 'install') { $store.Add($cert) } else { $store.Remove($cert) }
} finally {
    $store.Close()
}
"""


@dataclass
class ExeSignature:
    status: str
    subject: str
    timestamped: bool


def own_exe() -> Path | None:
    """O .exe em execução, ou None ao rodar como script."""
    if "__compiled__" not in globals():
        return None
    exe = Path(sys.argv[0]).resolve()
    return exe if exe.is_file() else None


def run_powershell(script: str, **variables: str) -> subprocess.CompletedProcess:
    """Usa o caminho completo porque o Windows procuraria primeiro na pasta atual."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    executable = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    wrapped = ("$ErrorActionPreference = 'Stop'\n[Console]::OutputEncoding = [Text.Encoding]::UTF8\n"
               f"try {{\n{script}\n}} catch {{\n[Console]::Error.WriteLine($_.Exception.Message)\nexit 1\n}}")
    # O PSModulePath herdado de um terminal com PowerShell 7 impede o 5.1 de carregar os próprios módulos.
    env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    try:
        return subprocess.run(
            [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "RemoteSigned", "-Command", wrapped],
            capture_output=True, stdin=subprocess.DEVNULL, encoding="utf-8-sig", errors="replace",
            env={**env, **variables}, timeout=300, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise OSError("o PowerShell não respondeu a tempo") from error


def read_signature(exe: Path | None = None) -> ExeSignature:
    result = run_powershell(
        READ_SIGNATURE_SCRIPT,
        ASTRAL_EXE=str(exe) if exe else "",
        ASTRAL_THUMBPRINT=EMBEDDED_CERT_THUMBPRINT,
    )
    fields = result.stdout.strip().split("|")
    if result.returncode != 0 or len(fields) != 3:
        raise OSError(f"não foi possível ler a assinatura: {result.stderr.strip()}")
    return ExeSignature(fields[0], fields[1], fields[2] == "True")


def change_trust(exe: Path | None, action: str) -> None:
    result = run_powershell(
        CHANGE_TRUST_SCRIPT,
        ASTRAL_EXE=str(exe) if exe else "",
        ASTRAL_STORE=TRUST_STORE,
        ASTRAL_ACTION=action,
        ASTRAL_CERT_B64=EMBEDDED_CERT_B64,
    )
    if result.returncode != 0:
        raise OSError(f"certificado não alterado: {result.stderr.strip()}")


# --------------------------------------------------------------------------- #
# TUI (sequências ANSI + msvcrt)
# --------------------------------------------------------------------------- #
BOLD, DIM, RED, GREEN, YELLOW, MAGENTA, CYAN, INVERSE = "1", "2", "31", "32", "33", "35", "36", "7"


def paint(text: str, *codes: str) -> str:
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def enable_vt() -> None:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_ulong()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def draw(lines: list[str]) -> None:
    """Redesenha sem limpar a tela (evita piscar); some com as linhas em branco se faltar altura."""
    rows = shutil.get_terminal_size((120, 30)).lines
    if len(lines) > rows:
        lines = [line for line in lines if line][-rows:]
    sys.stdout.write("\x1b[H" + "\x1b[K\n".join(lines) + "\x1b[K\x1b[J")
    sys.stdout.flush()


def read_key() -> str:
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        return {"H": "UP", "P": "DOWN"}.get(msvcrt.getwch(), "")
    if ch == "\x03":
        raise KeyboardInterrupt
    return {"\r": "ENTER", "\x1b": "ESC", " ": "ENTER"}.get(ch, ch.upper())


def select(title: str, items: list[str], default: int = 0) -> int | None:
    """Lista com cursor e rolagem. Retorna o índice escolhido ou None (Esc)."""
    index = default
    while True:
        visible = max(3, shutil.get_terminal_size((120, 30)).lines - len(title.splitlines()) - 5)
        start = max(0, min(index - visible // 2, len(items) - visible))
        lines = [paint(APP, BOLD, MAGENTA), *(paint(t, BOLD) for t in title.splitlines()), ""]
        for i, item in enumerate(items[start:start + visible], start):
            lines.append(paint(f"> {item}", INVERSE) if i == index else f"  {item}")
        lines += ["", paint("Setas: mover | Enter: escolher | Esc: voltar", DIM)]
        draw(lines)
        key = read_key()
        if key == "UP":
            index = (index - 1) % len(items)
        elif key == "DOWN":
            index = (index + 1) % len(items)
        elif key == "ENTER":
            return index
        elif key == "ESC":
            return None
        elif len(key) == 1 and key in "123456789" and int(key) <= len(items):
            index = int(key) - 1


def variant_label(name: str) -> str:
    low = name.lower()
    info = next((text for key, text in VARIANT_INFO.items() if low.startswith(key)), "")
    return f"{name:<20} {info}".rstrip()


def pick_profile(root: Path, level: Path) -> str | None:
    current = level
    while find_engine_ini(current) is None:
        kids = subdirs(current)
        if not kids:
            raise FileNotFoundError(f"Sem Engine.ini em {current.relative_to(root)}")
        if len(kids) == 1:
            current = kids[0]
            continue
        recommended = next((i for i, k in enumerate(kids) if "recommended" in k.name.lower()), 0)
        crumbs = pretty_profile(current.relative_to(root).as_posix())
        choice = select(f"Instalar: {crumbs}", [variant_label(k.name) for k in kids], recommended)
        if choice is None:
            return None
        current = kids[choice]
    return current.relative_to(root).as_posix()


@dataclass
class MenuItem:
    key: str
    text: str
    group: str
    active: bool = False


def menu_items(mgr: Manager) -> list[MenuItem]:
    items = []
    profile = mgr.state["profile"] or ""
    for level in level_dirs(mgr.root):
        number = level.name[0]
        name = level.name.split("-", 1)[1].strip()
        items.append(MenuItem(number, f"{name:<10} {LEVEL_INFO[number]}", "Perfis (um por vez; Enter instala)",
                              profile.startswith(level.name + "/")))
    for option in mgr.options:
        active = option.key in mgr.state["options"]
        items.append(MenuItem(option.key, f"[{'X' if active else ' '}] {option.label}",
                              "Opções extras (Enter liga/desliga)", active))
    group = "Gerenciar"
    items += [
        MenuItem("P", f"[{'X' if mgr.readonly else ' '}] Engine.ini somente leitura (Enter marca/desmarca)",
                 group, mgr.readonly),
        MenuItem("U", "Desinstalar tudo (restaura o Engine.ini original)", group),
        MenuItem("B", "Criar backup agora", group),
        MenuItem("R", "Restaurar um backup", group),
    ]
    if own_exe():
        items.append(MenuItem("C", "Assinatura e certificado do .exe", group))
    items += [MenuItem("D", "Dicas", group), MenuItem("Q", "Sair", group)]
    return items


def game_status() -> str:
    try:
        name = running_game_process()
    except OSError:
        return paint("não foi possível verificar: alterações bloqueadas", YELLOW)
    return paint(f"ABERTO ({name}): alterações bloqueadas", BOLD, RED) if name else paint("fechado", GREEN)


def draw_main(mgr: Manager, items: list[MenuItem], cursor: int, message: str) -> None:
    source = "embutidos no programa" if mgr.root == embedded_root() else str(mgr.root)
    lines = [
        f"{paint(APP, BOLD, MAGENTA)} {paint('| AION 2 Global (Steam)', DIM)}",
        f"{paint('Engine.ini:', DIM)} {mgr.ini}",
        f"{paint('Perfis:', DIM)} {source}",
        f"{paint('Instalado:', DIM)} "
        + paint(pretty_profile(mgr.state["profile"]), GREEN if mgr.state["profile"] else DIM),
        f"{paint('Jogo:', DIM)} {game_status()}",
    ]
    if mgr.changed_outside:
        lines.append(paint("Aviso: o Engine.ini mudou fora do programa (o jogo pode tê-lo regravado). "
                           "Reaplique se preciso.", YELLOW))
    lines += [paint(f"Aviso: {problem}", YELLOW) for problem in mgr.problems]
    group = None
    for i, item in enumerate(items):
        if item.group != group:
            group = item.group
            lines += ["", paint(group, BOLD, CYAN)]
        text = f" {item.key}  {item.text}"
        if i == cursor:
            lines.append(paint(text, INVERSE))
        else:
            lines.append(paint(text, GREEN) if item.active else text)
    lines.append("")
    for part in (message or paint("Setas + Enter, ou a tecla do item", DIM)).splitlines():
        lines.append(paint(part, RED) if message.startswith(("Erro", "Bloqueado")) else part)
    draw(lines)


# Os quatro primeiros tópicos são o Readme.txt do mod, traduzido.
TIPS = {
    "Perfis": """\
Very Low    Denoisers e SSR desativados
Default     Sombras e reflexos estáveis
Normal      Mais sombras e AO melhor; Sharp Shadows do Astral Vision e Volumetric Clouds opcionais
High        Nanite ativado contra pop-in em GPUs modernas; reduz o desempenho em placas antigas
Very High   Lumen e Nanite ativados, com todas as otimizações de nitidez""",
    "Variantes dos perfis": """\
TAA                 Otimizações de Temporal Anti-Aliasing; efeitos temporais minimizados
TSR                 Otimizações de Temporal Super Resolution; nitidez máxima, sem os efeitos do TAA
Astral Shadows      Sombras nítidas exclusivas do Astral Vision
Astral Clouds       Nuvens ocultas do AION 2; grande ganho de desempenho em placas antigas
Volumetric Clouds   Nuvens padrão""",
    "Se algo não ficar bom": """\
Nítido demais, prefere a suavidade padrão   No jogo: Upscaler TAA
Continua nítido demais                      No jogo: Post-Processing Quality VeryLow
Sombras nítidas ou pixeladas demais         Variante Default Shadows
Quer as nuvens padrão de volta              Variante Volumetric Clouds
Perdeu FPS ou desempenho                    Perfil Normal""",
    "Configurações recomendadas no jogo": """\
Resolution Scale          Native
Effect Quality            VeryLow ou Low
Shadow Quality            VeryLow, Low ou Normal
Shading Quality           VeryLow ou Low
Post-Processing Quality   VeryLow (Low para mais nitidez)
Upscaler                  TSR, FSR, DLSS ou XeSS

Para reduzir a sensibilidade à luz:
Accessibility > Visual Assist > White Point Reduction""",
    "Steam Launch Options": f"""\
Recomendadas pelo mod (Additions.txt):

  {STEAM_LAUNCH}

Cole em: Steam > AION 2 > Propriedades > Geral > Opções de inicialização""",
    "SCSKiller: compilar os shaders": """\
O SCSKiller compila os shaders antes de você jogar e deixa o jogo mais fluido.
É gratuito, de código aberto e funciona com GPU NVIDIA ou AMD.

  https://github.com/BlueHeisenberg/SCSKiller

Baixe só pelas Releases desse repositório e compile com o jogo fechado.

Não ative o gravador (recorder) no AION 2: ele coloca uma d3d12.dll na pasta do jogo, e o próprio
SCSKiller avisa que isso pode dar ban em jogos com anti-cheat e que a detecção dele pode falhar.
Não é uma ferramenta deste projeto: use por sua conta e risco.""",
    "Somente leitura": """\
Marcado, o jogo não consegue regravar o Engine.ini. É o que a página do mod orienta.

Se o jogo não salvar uma mudança de upscaler ou de Frame Generation:
desmarque, feche o programa, mude no jogo, feche o jogo e marque de novo.

O programa continua podendo instalar com o arquivo marcado, e a marca é mantida.
Desinstalar tudo devolve o arquivo ao estado original, sem a marca.""",
    "Ajustes para a versão Steam": """\
Arquivo: %LOCALAPPDATA%\\AION2\\Saved_Steam\\Config\\Windows\\Engine.ini
Jogo: AION2.exe, em Aion2\\Binaries\\Win64. Com ele aberto, nada no Engine.ini é alterado.

O perfil é mesclado: [Core.System] e a escolha de upscaler feita no jogo são mantidos.

O jogo traz FSR 4, e as chaves r.FidelityFX.FSR3.* do mod são do plugin antigo. A opção
FSR / DLSS / XeSS grava também os nomes atuais, r.FidelityFX.FSR.*.
r.FidelityFX.FSR.QualityMode=0 fixa o FSR em Native AA, igual à intenção do mod.

A instalação Steam não traz DLL do XeSS: as chaves de XeSS não devem ter efeito.""",
    "Como este programa funciona": f"""\
Um perfil por vez: instalar outro substitui o atual.
O 1º uso cria {ORIGINAL_BAK} ao lado do Engine.ini.
Cada instalação recalcula: backup original + perfil + opções extras.
Se o arquivo mudou fora do programa, uma cópia '-auto' é salva antes de sobrescrever.""",
    "Assinatura do .exe": """\
O programa utiliza um certificado autoassinado fixo com carimbo de tempo oficial da DigiCert.
O certificado público fica embutido no programa e assinado no .exe; a chave privada fica protegida
nos Secrets do repositório no GitHub para os builds e releases automáticas.

Até instalar o certificado, o Windows não reconhece a assinatura. O programa pergunta no 1º uso,
e a tecla C abre o mesmo menu depois, também para remover.
Ao instalar o certificado uma vez neste usuário, o Windows passa a reconhecer todas as versões
oficiais do Astral Vision como confiáveis. Instale apenas se você confia em quem gerou o .exe.""",
}


def tips_menu() -> None:
    titles = list(TIPS)
    index = 0
    while True:
        choice = select("Dicas", titles, index)
        if choice is None:
            return
        index = choice
        title = titles[index]
        draw([paint(f"Dicas: {title}", BOLD, MAGENTA), "", *TIPS[title].splitlines(), "",
              paint("Qualquer tecla para voltar", DIM)])
        read_key()


def restore_menu(mgr: Manager) -> str:
    backups = mgr.list_backups()
    if not backups:
        return "Nenhum backup encontrado."
    labels = []
    for backup in backups:
        when = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
        labels.append(f"{backup.name:<46} {when}" + ("  ORIGINAL" if backup == mgr.original else ""))
    choice = select("Restaurar qual backup?", labels)
    return "" if choice is None else mgr.restore(backups[choice])


def level_action(mgr: Manager, level: Path) -> str:
    options = list(mgr.state["options"])
    profile = mgr.state["profile"] or ""
    if profile.startswith(level.name + "/"):
        choice = select(f"Já instalado: {pretty_profile(profile)}", ["Trocar variante", "Desinstalar este perfil"])
        if choice is None:
            return ""
        if choice == 1:
            return mgr.apply(None, options)
    rel = pick_profile(mgr.root, level)
    return mgr.apply(rel, options) if rel else ""


def signature_menu(exe: Path | None, signature: ExeSignature, first_run: bool = False) -> str:
    if signature.status == "Valid" and first_run:
        return ""
    if signature.status == "NotSigned":
        return "Este executável não tem assinatura. Gere um assinado com o build.ps1."
    if signature.status == "HashMismatch":
        return "Erro: o arquivo foi alterado depois de assinado. Não instale este certificado."
    details = [
        "Primeira execução: assinatura do programa" if first_run else "Assinatura do programa",
        f"Assinante: {signature.subject}",
        f"Carimbo de tempo da DigiCert: {'sim' if signature.timestamped else 'não'}",
    ]
    if signature.status == "Valid":
        details.append("O Windows já reconhece este certificado neste usuário.")
        if select("\n".join(details), ["Remover o certificado deste usuário", "Voltar"], 1) != 0:
            return ""
        action = "remove"
    else:
        details += [
            "O certificado autoassinado fixo está integrado ao programa e autenticado com",
            "carimbo de tempo da DigiCert. O Windows reconhece a assinatura após instalá-lo.",
        ]
        options = ["Instalar o certificado fixo (o Windows pede confirmação)", "Agora não"]
        if select("\n".join(details), options) != 0:
            return "Certificado não instalado. Use a tecla C quando quiser."
        action = "install"
    draw([paint(APP, BOLD, MAGENTA), "", "Aguardando o Windows: confirme a janela de segurança, se ela aparecer."])
    change_trust(exe, action)
    status = read_signature(exe).status
    if action == "remove":
        return "Certificado removido. O programa continua assinado, mas o Windows não reconhece mais a assinatura."
    if status == "Valid":
        return "Certificado instalado: o Windows reconhece o programa como confiável."
    return f"Certificado instalado, mas a assinatura continua como {status}."


def first_run_signature(mgr: Manager) -> str:
    exe = own_exe()
    try:
        signature = read_signature(exe)
    except Exception:
        return ""
    if signature.status == "Valid":
        return ""
    if mgr.state.get("sign_asked") == EMBEDDED_CERT_THUMBPRINT:
        return ""
    mgr.state["sign_asked"] = EMBEDDED_CERT_THUMBPRINT
    mgr.save_state()
    return signature_menu(exe, signature, first_run=True)


def handle(mgr: Manager, key: str) -> str:
    if key == "D":
        tips_menu()
        return ""
    if key == "C":
        exe = own_exe()
        return signature_menu(exe, read_signature(exe))
    if key == "B":
        backup = mgr.backup_now()
        return f"Backup criado: {backup.name}" if backup else "Engine.ini não existe: nada a copiar."
    require_game_closed()  # daqui em diante, tudo altera o Engine.ini
    level = next((d for d in level_dirs(mgr.root) if d.name[0] == key), None)
    if level:
        return level_action(mgr, level)
    if key in {option.key for option in mgr.options}:
        options = list(mgr.state["options"])
        options.remove(key) if key in options else options.append(key)
        return mgr.apply(mgr.state["profile"], options)
    if key == "P":
        return mgr.toggle_readonly()
    if key == "U":
        choice = select("Desinstalar tudo e restaurar o Engine.ini original?", ["Sim, restaurar", "Não"], 1)
        return mgr.uninstall() if choice == 0 else ""
    if key == "R":
        return restore_menu(mgr)
    return ""


def run_tui(mgr: Manager, message: str) -> None:
    try:
        message = "\n".join(filter(None, [message, first_run_signature(mgr)]))
    except OSError as error:
        message = f"Erro: {error}"
    cursor = 0
    while True:
        items = menu_items(mgr)
        draw_main(mgr, items, cursor, message)
        key = read_key()
        if key == "UP":
            cursor = (cursor - 1) % len(items)
        elif key == "DOWN":
            cursor = (cursor + 1) % len(items)
        else:
            message = ""
            if key == "ENTER":
                key = items[cursor].key
            match = next((i for i, item in enumerate(items) if item.key == key), None)
            if match is None:
                continue
            cursor = match
            if key == "Q":
                return
            try:
                message = handle(mgr, key)
            except GameRunning as error:
                message = str(error)
            except OSError as error:
                message = f"Erro: {error}"


def fail(text: str) -> int:
    print(text)
    print("\nQualquer tecla para sair.")
    read_key()
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=f"{APP}: perfis do Engine.ini do AION 2 Global (Steam)")
    parser.add_argument("--ini", help="Caminho do Engine.ini (padrão: %%LOCALAPPDATA%%\\AION2\\Saved_Steam\\Config\\Windows)")
    parser.add_argument("--profiles", help="Pasta com os perfis (padrão: pasta do programa, pasta atual, embutidos)")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    enable_vt()

    ini = Path(args.ini) if args.ini else default_ini()
    if not ini.parent.is_dir():
        return fail(f"Pasta de configuração não encontrada:\n  {ini.parent}\n\n"
                    "Abra o AION 2 pela Steam uma vez, ou informe o caminho com --ini.")
    root = find_profiles_root(args.profiles)
    if root is None:
        return fail("Nenhuma pasta de perfil (1- a 5-) encontrada.")

    manager = Manager(ini, root)
    message = manager.ensure_original() or ""

    sys.stdout.write("\x1b]0;Astral Vision\x07\x1b[?1049h\x1b[?25l\x1b[2J")
    try:
        run_tui(manager, message)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:  # a janela fecharia sem mostrar nada ao abrir com dois cliques
        sys.exit(fail(f"Erro: {error}"))
