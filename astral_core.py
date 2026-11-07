"""Núcleo do Astral Vision: Engine.ini, perfis, opções, backups, assinatura e serviço de energia.

Usa apenas a biblioteca padrão: o serviço de energia importa só este módulo, sem carregar a interface.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time
import uuid
import winreg
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
# Steam: Aion2\Binaries\Win64\AION2.exe. O nome interno do executável é Aion2-Win64-Shipping.exe.
GAME_PROCESSES = {"aion2.exe", "aion.exe", "aion2-win64-shipping.exe"}
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
    ("V", "VSync.txt", "VSync desligado"),
    ("T", "Distance View Low.txt", "Distance View Low: reduz a distância de players, mobs e objetos"),
    ("H", "Distance View High.txt", "Distance View High: distância máxima de players, mobs, objetos e texturas"),
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


def list_processes() -> list[tuple[int, str]]:
    """(PID, nome do .exe) de cada processo, sem abrir handle para eles. Se não der para listar, levanta OSError."""
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
    processes = []
    try:
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            processes.append((entry.th32ProcessID, entry.szExeFile))
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return processes


def running_game_process() -> str | None:
    """Nome do processo do jogo em execução. Se não der para verificar, levanta OSError."""
    return next((name for _, name in list_processes() if name.lower() in GAME_PROCESSES), None)


class GameRunning(Exception):
    """O jogo está aberto: o Engine.ini não pode ser alterado."""


def require_game_closed() -> None:
    name = running_game_process()
    if name:
        raise GameRunning(f"Bloqueado: feche o jogo ({name}) antes de alterar o Engine.ini.")


# --------------------------------------------------------------------------- #
# Serviço de energia: plano de alto desempenho com o jogo em foco
# --------------------------------------------------------------------------- #
# IDs dos planos que vêm com o Windows. O Desempenho Máximo costuma existir só como cópia, com um ID aleatório
# em cada PC: por isso também é reconhecido pelo nome, que a API devolve no idioma do sistema.
PLAN_ULTIMATE = "e9a42b02-d5df-448d-aa00-03f14749eb61"  # Desempenho Máximo, original
PLAN_HIGH = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"      # Alto desempenho
PLAN_BALANCED = "381b4222-f694-41f0-9685-ff5bb260df2e"  # Equilibrado
PLAN_PERSONALITY = "245d8541-3943-4422-b025-13a784f679b7"  # configuração oculta: o tipo de que o plano deriva
NO_SUBGROUP = "fea3413e-7e05-4911-9a71-700331f1c294"
PERSONALITY_HIGH = 1  # 0: economia de energia, 1: alto desempenho, 2: equilibrado
# Um Windows Service roda na sessão 0 e não enxerga a janela em foco do usuário. Por isso o serviço é
# este mesmo programa, sem janela, iniciado no logon pela chave Run do usuário (não precisa de admin).
SERVICE_ARG = "--power-service"
SERVICE_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SERVICE_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
SERVICE_RUN_VALUE = "Astral Vision Power"
SERVICE_MUTEX = r"Local\AstralVisionPowerService"
SERVICE_STOP_EVENT = r"Local\AstralVisionPowerServiceStop"
SERVICE_INTERVAL_MS = 1000
SERVICE_RETRY_MS = 30000  # depois de um erro: não repete a tentativa a cada segundo

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateMutexW.restype = wintypes.HANDLE
_kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.OpenMutexW.restype = wintypes.HANDLE
_kernel32.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.CreateEventW.restype = wintypes.HANDLE
_kernel32.CreateEventW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.OpenEventW.restype = wintypes.HANDLE
_kernel32.OpenEventW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
_kernel32.SetEvent.argtypes = (wintypes.HANDLE,)
_kernel32.ResetEvent.argtypes = (wintypes.HANDLE,)
_kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
_kernel32.WaitForSingleObject.restype = wintypes.DWORD
_kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
_user32 = ctypes.WinDLL("user32")
_user32.GetForegroundWindow.restype = wintypes.HWND
_user32.GetWindowThreadProcessId.restype = wintypes.DWORD
_user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
_kernel32.GetConsoleWindow.restype = wintypes.HWND
_kernel32.LocalFree.restype = wintypes.LPVOID
_kernel32.LocalFree.argtypes = (wintypes.LPVOID,)
_shell32 = ctypes.WinDLL("shell32")
_shell32.Shell_NotifyIconW.argtypes = (wintypes.DWORD, ctypes.c_void_p)
_shell32.Shell_NotifyIconW.restype = wintypes.BOOL
_shell32.ExtractIconW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT)
_shell32.ExtractIconW.restype = wintypes.HICON
_user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.DefWindowProcW.restype = ctypes.c_ssize_t
_user32.IsIconic.argtypes = (wintypes.HWND,)
_user32.IsIconic.restype = wintypes.BOOL
_user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.ShowWindow.restype = wintypes.BOOL
_user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
_user32.SetForegroundWindow.restype = wintypes.BOOL
_user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.PostMessageW.restype = wintypes.BOOL
_user32.LoadImageW.argtypes = (wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT)
_user32.LoadImageW.restype = wintypes.HANDLE
_user32.CreatePopupMenu.restype = wintypes.HMENU
_user32.AppendMenuW.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR)
_user32.AppendMenuW.restype = wintypes.BOOL
_user32.TrackPopupMenu.argtypes = (wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPVOID)
_user32.TrackPopupMenu.restype = ctypes.c_int
_user32.DestroyMenu.argtypes = (wintypes.HMENU,)
_user32.DestroyMenu.restype = wintypes.BOOL
_powrprof = ctypes.WinDLL("powrprof")
_powrprof.PowerEnumerate.argtypes = (wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, ctypes.c_int, wintypes.ULONG,
                                     wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD))
_powrprof.PowerReadFriendlyName.argtypes = (wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
                                            wintypes.LPVOID, ctypes.POINTER(wintypes.DWORD))
_powrprof.PowerReadACValueIndex.argtypes = (wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID,
                                            ctypes.POINTER(wintypes.DWORD))
_powrprof.PowerGetActiveScheme.argtypes = (wintypes.LPVOID, ctypes.POINTER(wintypes.LPVOID))
_powrprof.PowerSetActiveScheme.argtypes = (wintypes.LPVOID, wintypes.LPVOID)
# Lido ao importar, antes de open_console(): só o build sem console consegue rodar o serviço sem abrir janela.
STARTED_WITHOUT_CONSOLE = not _kernel32.GetConsoleWindow()


def service_supported() -> bool:
    """O serviço existe no script e no build local. A release tem console e não o traz: o Defender a bloquearia."""
    return "__compiled__" not in globals() or STARTED_WITHOUT_CONSOLE


@dataclass
class PowerPlan:
    guid: str
    name: str
    personality: int | None


def _guid(text: str) -> ctypes.Array:
    return ctypes.create_string_buffer(uuid.UUID(text).bytes_le, 16)


def plan_name(guid: str) -> str:
    """Nome no idioma do Windows, ou vazio se o Windows não conhecer o plano."""
    key = _guid(guid)
    size = wintypes.DWORD(0)
    if _powrprof.PowerReadFriendlyName(None, key, None, None, None, ctypes.byref(size)) not in (0, 234):  # MORE_DATA
        return ""
    buffer = ctypes.create_string_buffer(size.value + 2)
    if _powrprof.PowerReadFriendlyName(None, key, None, None, buffer, ctypes.byref(size)):
        return ""
    return ctypes.wstring_at(buffer)


def plan_personality(guid: str) -> int | None:
    value = wintypes.DWORD()
    code = _powrprof.PowerReadACValueIndex(None, _guid(guid), _guid(NO_SUBGROUP), _guid(PLAN_PERSONALITY),
                                           ctypes.byref(value))
    return None if code else value.value


def list_plans() -> list[PowerPlan]:
    """Mapeia os planos deste PC pela API do Windows: não depende de idioma nem de IDs fixos."""
    plans = []
    while True:
        buffer = ctypes.create_string_buffer(16)
        size = wintypes.DWORD(16)
        code = _powrprof.PowerEnumerate(None, None, None, 16, len(plans), buffer, ctypes.byref(size))  # ACCESS_SCHEME
        if code == 259:  # ERROR_NO_MORE_ITEMS
            return plans
        if code:
            raise ctypes.WinError(code)
        guid = str(uuid.UUID(bytes_le=buffer.raw))
        plans.append(PowerPlan(guid, plan_name(guid), plan_personality(guid)))


def choose_boost(plans: list[PowerPlan], ultimate_name: str, high_name: str) -> PowerPlan | None:
    """Desempenho Máximo, se existir; senão Alto desempenho; senão outro plano derivado dele, como o de um fabricante."""
    ult_names = {"desempenho máximo", "ultimate performance"} | ({ultimate_name.lower()} if ultimate_name else set())
    high_names = {"alto desempenho", "high performance"} | ({high_name.lower()} if high_name else set())
    tests = (
        lambda plan: plan.guid == PLAN_ULTIMATE or plan.name.strip().lower() in ult_names,
        lambda plan: plan.guid == PLAN_HIGH or plan.name.strip().lower() in high_names,
        lambda plan: plan.personality == PERSONALITY_HIGH,
    )
    for test in tests:
        found = next((plan for plan in plans if test(plan)), None)
        if found:
            return found
    return None


def boost_plan() -> PowerPlan | None:
    return choose_boost(list_plans(), plan_name(PLAN_ULTIMATE), plan_name(PLAN_HIGH))


def boost_label() -> str:
    try:
        boost = boost_plan()
    except OSError:
        boost = None
    return boost.name if boost else "alto desempenho"


def no_boost_message() -> str:
    names = ", ".join(plan.name for plan in list_plans())
    return f"este PC não tem plano de alto desempenho (planos encontrados: {names})"


def active_plan() -> str:
    pointer = wintypes.LPVOID()
    code = _powrprof.PowerGetActiveScheme(None, ctypes.byref(pointer))
    if code:
        raise ctypes.WinError(code)
    try:
        return str(uuid.UUID(bytes_le=ctypes.string_at(pointer, 16)))
    finally:
        _kernel32.LocalFree(pointer)


def set_plan(guid: str) -> None:
    code = _powrprof.PowerSetActiveScheme(None, _guid(guid))
    if code:
        raise ctypes.WinError(code)


def foreground_process_id() -> int:
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def service_state_path() -> Path:
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / "AstralVision" / "power-service.json"


def read_service_state() -> dict:
    try:
        return json.loads(service_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_service_state(**changes) -> None:
    path = service_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_file(path, json.dumps({**read_service_state(), **changes}).encode("utf-8"))


def restore_saved_plan() -> None:
    """Volta ao plano que estava ativo antes de o jogo ganhar o foco, se houver um guardado."""
    before = read_service_state().get("before")
    if not before:
        return
    try:
        set_plan(before)
    except OSError:
        set_plan(PLAN_BALANCED)  # o plano guardado foi apagado
    write_service_state(before=None)


class SessionPowerFocus:
    """Troca de plano só nesta sessão, preservando uma escolha externa posterior."""

    def __init__(self) -> None:
        self.applied: tuple[str, str] | None = None
        self.focused = False

    def tick(self) -> None:
        pid = foreground_process_id()
        self.focused = bool(pid and any(number == pid and name.lower() in GAME_PROCESSES
                                        for number, name in list_processes()))
        if self.focused and self.applied is None:
            boost = boost_plan()
            if boost is None:
                raise OSError(no_boost_message())
            previous = active_plan()
            set_plan(boost.guid)
            self.applied = (previous, boost.guid)
        elif not self.focused:
            self.restore()

    def restore(self) -> None:
        self.focused = False
        if self.applied is not None:
            previous, selected = self.applied
            if active_plan() == selected:
                set_plan(previous)
            self.applied = None


class PowerFocus:
    """Com o jogo em foco usa o plano mais rápido; fora de foco, volta ao plano que estava ativo antes.

    O plano anterior fica gravado em disco: se o PC desligar com o jogo em foco, o plano ativo continuaria
    sendo o mais rápido, e o serviço o restaura ao iniciar de novo.
    """

    def __init__(self) -> None:
        self.pid = 0
        self.focused = False
        self.engaged = bool(read_service_state().get("before"))

    def tick(self) -> None:
        pid = foreground_process_id()
        if pid != self.pid:  # lista os processos só quando o foco muda
            self.focused = pid != 0 and any(
                number == pid and name.lower() in GAME_PROCESSES for number, name in list_processes())
            self.pid = pid
        if self.focused and not self.engaged:
            boost = boost_plan()
            if boost is None:
                raise OSError(no_boost_message())
            write_service_state(before=active_plan())
            set_plan(boost.guid)
            self.engaged = True
        elif not self.focused and self.engaged:
            restore_saved_plan()
            self.engaged = False


def run_power_service() -> int:
    """Modo sem janela (--power-service). Só uma instância por sessão; termina pelo evento de parada."""
    mutex = _kernel32.CreateMutexW(None, False, SERVICE_MUTEX)
    if not mutex:
        return 0
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        _kernel32.CloseHandle(mutex)
        return 0
    stop = _kernel32.CreateEventW(None, True, False, SERVICE_STOP_EVENT)
    _kernel32.ResetEvent(stop)
    focus = PowerFocus()
    reported = read_service_state().get("error")
    wait = 0
    while _kernel32.WaitForSingleObject(stop, wait) != 0:  # WAIT_OBJECT_0
        try:
            focus.tick()
            problem = None
        except Exception as error:  # roda sozinho e sem janela: o menu mostra o erro, e o serviço tenta de novo
            problem = str(error)
        wait = SERVICE_RETRY_MS if problem else SERVICE_INTERVAL_MS
        if problem != reported:
            reported = problem
            try:
                write_service_state(error=problem)
            except OSError:
                pass
    try:
        restore_saved_plan()
    except OSError:
        pass  # o menu tenta de novo em stop_service
    _kernel32.CloseHandle(stop)
    _kernel32.CloseHandle(mutex)
    return 0


def service_command() -> str:
    exe = own_exe()
    if exe:
        return f'"{exe}" {SERVICE_ARG}'
    script = Path(__file__).resolve().with_name("astral_vision.py")
    return f'"{Path(sys.executable).with_name("pythonw.exe")}" "{script}" {SERVICE_ARG}'


def registered_service() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SERVICE_RUN_KEY) as key:
            return winreg.QueryValueEx(key, SERVICE_RUN_VALUE)[0]
    except OSError:
        return None


def register_service(command: str | None) -> None:
    """Grava ou remove o início no logon, e tira o bloqueio do Gerenciador de Tarefas sobre o valor antigo."""
    for path, write in ((SERVICE_APPROVED_KEY, False), (SERVICE_RUN_KEY, bool(command))):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_SET_VALUE) as key:
                if write:
                    winreg.SetValueEx(key, SERVICE_RUN_VALUE, 0, winreg.REG_SZ, command)
                else:
                    winreg.DeleteValue(key, SERVICE_RUN_VALUE)
        except FileNotFoundError:
            pass  # a chave ou o valor não existem: nada a remover


def service_running() -> bool:
    handle = _kernel32.OpenMutexW(0x00100000, False, SERVICE_MUTEX)  # SYNCHRONIZE
    if handle:
        _kernel32.CloseHandle(handle)
    return bool(handle)


def wait_service(running: bool, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while service_running() != running and time.monotonic() < deadline:
        time.sleep(0.1)
    return service_running() == running


def start_service(command: str) -> None:
    # Variáveis do .exe em onefile não podem passar para o outro processo do mesmo .exe.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("NUITKA_")}
    subprocess.Popen(
        command, cwd=Path.home(), env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    if not wait_service(True, 15):
        raise OSError("o serviço de energia não iniciou")


def stop_service() -> None:
    handle = _kernel32.OpenEventW(0x0002, False, SERVICE_STOP_EVENT)  # EVENT_MODIFY_STATE
    if handle:
        _kernel32.SetEvent(handle)
    stopped = wait_service(False, 10)
    if handle:
        _kernel32.CloseHandle(handle)
    if not stopped:
        raise OSError("o serviço de energia não parou a tempo")
    restore_saved_plan()  # cobre um serviço que foi encerrado à força


def toggle_power_service() -> str:
    if registered_service():
        register_service(None)
        stop_service()
        return "Serviço de energia DESLIGADO: voltou ao plano anterior e não inicia mais com o Windows."
    boost = boost_plan()
    if boost is None:
        return f"Erro: {no_boost_message()}."
    command = service_command()
    register_service(command)
    if not service_running():
        start_service(command)
    return (f"Serviço de energia LIGADO: {boost.name} com o jogo em foco; "
            "roda sem o programa aberto e inicia com o Windows.")


def sync_service() -> None:
    """Ao abrir o menu: se ligado, garante que o serviço roda a partir deste .exe; se desligado, que está parado."""
    command = registered_service()
    if not command:
        if service_running():
            stop_service()
        return
    if own_exe() and command != service_command():  # o .exe mudou de lugar ou de versão
        stop_service()
        command = service_command()
        register_service(command)
    if not service_running():
        start_service(command)


def clean_old_unpacked() -> None:
    """O .exe se extrai numa pasta fixa por build (ver build.ps1): apaga as pastas de builds anteriores."""
    if "__compiled__" not in globals():
        return
    current = Path(__file__).resolve().parent
    if current.parent.name != "app" or current.parent.parent.name != "AstralVision":
        return
    for folder in current.parent.iterdir():
        if folder != current and folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)


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
            "sign_asked": None,  # hash do .exe já perguntado, para não repetir a pergunta na mesma versão
            "power_focus": True,
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
# O build.ps1 assina com um certificado autoassinado fixo e carimbo de tempo da DigiCert. A assinatura guarda
# o certificado público dentro do .exe; a chave privada fica no PC do build local ou nos Secrets das releases.
TRUST_STORE = "Root"
READ_SIGNATURE_SCRIPT = r"""
$signature = Get-AuthenticodeSignature -LiteralPath $env:ASTRAL_EXE
'{0}|{1}|{2}' -f $signature.Status, $signature.SignerCertificate.Subject, [bool]$signature.TimeStamperCertificate
"""
CHANGE_TRUST_SCRIPT = r"""
$certificate = (Get-AuthenticodeSignature -LiteralPath $env:ASTRAL_EXE).SignerCertificate
if (-not $certificate) { throw 'O .exe nao tem assinatura.' }
$store = [Security.Cryptography.X509Certificates.X509Store]::new($env:ASTRAL_STORE, 'CurrentUser')
$store.Open('ReadWrite')
try {
    if ($env:ASTRAL_ACTION -eq 'install') { $store.Add($certificate) } else { $store.Remove($certificate) }
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


def read_signature(exe: Path) -> ExeSignature:
    result = run_powershell(READ_SIGNATURE_SCRIPT, ASTRAL_EXE=str(exe))
    fields = result.stdout.strip().split("|")
    if result.returncode != 0 or len(fields) != 3:
        raise OSError(f"não foi possível ler a assinatura: {result.stderr.strip()}")
    return ExeSignature(fields[0], fields[1], fields[2] == "True")


def change_trust(exe: Path, action: str) -> None:
    result = run_powershell(CHANGE_TRUST_SCRIPT, ASTRAL_EXE=str(exe), ASTRAL_STORE=TRUST_STORE, ASTRAL_ACTION=action)
    if result.returncode != 0:
        raise OSError(f"certificado não alterado: {result.stderr.strip()}")


def copy_to_clipboard(text: str) -> None:
    """Usa o caminho completo porque o Windows procuraria primeiro na pasta atual."""
    clip = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "clip.exe"
    try:
        subprocess.run([str(clip)], input=text.encode("utf-16-le"), check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
    except (subprocess.SubprocessError, OSError) as error:
        raise OSError(f"não foi possível copiar: {error}") from error


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uTimeoutOrVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wintypes.HICON),
    ]


_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HICON),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class TrayManager:
    """Minimiza a interface para a bandeja do sistema (System Tray / perto do relógio)."""

    def __init__(self, on_restore=None, on_quit=None) -> None:
        self.on_restore = on_restore
        self.on_quit = on_quit
        self.hwnd_app = 0
        self.hwnd_msg = 0
        self.in_tray = False
        self.stop_event = threading.Event()
        self._ready = threading.Event()
        self.thread: threading.Thread | None = None
        self._proc_ref = None

    def start(self, hwnd_app: int | None = None) -> None:
        self.hwnd_app = hwnd_app or _kernel32.GetConsoleWindow() or 0
        self._ready.clear()
        self.thread = threading.Thread(target=self._run_msg_loop, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=2.0)

    def check_minimized(self) -> None:
        """Verifica se a janela foi minimizada pelo usuário e a move para a bandeja."""
        if not self.hwnd_app:
            self.hwnd_app = _kernel32.GetConsoleWindow() or 0
        if self.hwnd_app and not self.in_tray:
            if _user32.IsIconic(self.hwnd_app):
                self.minimize()

    def minimize(self) -> None:
        if not self.hwnd_app:
            self.hwnd_app = _kernel32.GetConsoleWindow() or 0
        if not self.hwnd_app or self.in_tray:
            return
        self.in_tray = True
        _user32.ShowWindow(self.hwnd_app, 0)  # SW_HIDE
        self._add_icon()

    def restore(self) -> None:
        if not self.in_tray:
            return
        self._remove_icon()
        if self.hwnd_app:
            _user32.ShowWindow(self.hwnd_app, 9)  # SW_RESTORE
            _user32.SetForegroundWindow(self.hwnd_app)
        self.in_tray = False
        if self.on_restore:
            try:
                self.on_restore()
            except Exception:
                pass

    def stop(self) -> None:
        self.stop_event.set()
        if self.in_tray:
            self.restore()
        self._remove_icon()
        if self.hwnd_msg:
            _user32.PostMessageW(self.hwnd_msg, 0x0012, 0, 0)  # WM_QUIT
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)

    def _run_msg_loop(self) -> None:
        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == 0x0400 + 35:
                if lparam in (0x0202, 0x0203):  # WM_LBUTTONUP, WM_LBUTTONDBLCLK
                    self.restore()
                    return 0
                elif lparam == 0x0205:  # WM_RBUTTONUP
                    self._show_menu()
                    return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._proc_ref = _WNDPROC(wnd_proc)
        hinst = _kernel32.GetModuleHandleW(None)
        cls_name = f"AstralTray_{os.getpid()}"
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.lpfnWndProc = self._proc_ref
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        _user32.RegisterClassExW(ctypes.byref(wc))

        self.hwnd_msg = _user32.CreateWindowExW(0, cls_name, "", 0, 0, 0, 0, 0, 0, 0, hinst, None)
        self._ready.set()

        msg = wintypes.MSG()
        while not self.stop_event.is_set():
            ret = _user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if ret <= 0:
                break
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

        if self.hwnd_msg:
            _user32.DestroyWindow(self.hwnd_msg)
            self.hwnd_msg = 0
        _user32.UnregisterClassW(cls_name, hinst)

    def _show_menu(self) -> None:
        menu = _user32.CreatePopupMenu()
        _user32.AppendMenuW(menu, 0, 1, "Restaurar")
        _user32.AppendMenuW(menu, 0x00000800, 0, "")  # MF_SEPARATOR
        _user32.AppendMenuW(menu, 0, 2, "Sair")
        pos = wintypes.POINT()
        _user32.GetCursorPos(ctypes.byref(pos))
        _user32.SetForegroundWindow(self.hwnd_msg)
        cmd = _user32.TrackPopupMenu(menu, 0x0100, pos.x, pos.y, 0, self.hwnd_msg, None)  # TPM_RETURNCMD
        _user32.DestroyMenu(menu)
        if cmd == 1:
            self.restore()
        elif cmd == 2:
            if self.on_quit:
                self.on_quit()
            else:
                self.restore()

    def _add_icon(self) -> None:
        if not self.hwnd_msg:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd_msg
        nid.uID = 101
        nid.uFlags = 0x01 | 0x02 | 0x04 | 0x10  # NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
        nid.uCallbackMessage = 0x0400 + 35
        exe_path = sys.executable or str(Path(sys.argv[0]).resolve())
        h_icon = _shell32.ExtractIconW(_kernel32.GetModuleHandleW(None), exe_path, 0)
        if not h_icon or h_icon == 1:
            for candidate in (app_dir() / "astral_vision.ico", Path(__file__).resolve().parent / "astral_vision.ico"):
                if candidate.is_file():
                    h_icon = _user32.LoadImageW(0, str(candidate), 1, 16, 16, 0x00000010)
                    if h_icon:
                        break
        if not h_icon or h_icon == 1:
            h_icon = _user32.LoadIconW(0, 32512)
        nid.hIcon = h_icon
        nid.szTip = "AION 2 Astral Vision (Clique para restaurar)"
        nid.szInfoTitle = "Astral Vision"
        nid.szInfo = "Programa minimizado na bandeja do sistema."
        nid.dwInfoFlags = 0x01  # NIIF_INFO
        _shell32.Shell_NotifyIconW(0, ctypes.byref(nid))

    def _remove_icon(self) -> None:
        if not self.hwnd_msg:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd_msg
        nid.uID = 101
        _shell32.Shell_NotifyIconW(2, ctypes.byref(nid))
