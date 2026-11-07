#!/usr/bin/env python3
"""Astral Vision: instalador de perfis para o Engine.ini do AION 2 Global (Steam).

Mescla um perfil (pastas 1- a 5-) e as opções extras (.txt) no Engine.ini do jogo,
mantendo um backup original ao lado do arquivo.

Uso:  AstralVision.exe [--ini CAMINHO\\Engine.ini] [--profiles PASTA]
"""
from __future__ import annotations

import argparse
import ctypes
import msvcrt
import os
import sys
from ctypes import wintypes
from pathlib import Path

import astral_core as core


def open_console() -> None:
    """O .exe do build local é compilado sem console, para o serviço não abrir janela; a interface cria o dela."""
    if "__compiled__" not in globals() or not core._kernel32.AllocConsole():
        return
    # O Nuitka deixou stdin, stdout e stderr em NUL: liga os descritores 0, 1 e 2 ao console novo.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream:
            stream.close()
    core._kernel32.SetStdHandle.argtypes = (wintypes.DWORD, wintypes.HANDLE)
    for number, handle_id, device in ((0, -10, "CONIN$"), (1, -11, "CONOUT$"), (2, -12, "CONOUT$")):
        fd = os.open(device, os.O_RDWR)  # GetConsoleMode exige leitura também no CONOUT$
        if fd != number:
            os.dup2(fd, number)
            os.close(fd)
        core._kernel32.SetStdHandle(handle_id, msvcrt.get_osfhandle(number))
    sys.stdin = sys.__stdin__ = open(0, encoding="utf-8", closefd=False)
    sys.stdout = sys.__stdout__ = open(1, "w", encoding="utf-8", errors="replace", closefd=False)
    sys.stderr = sys.__stderr__ = open(2, "w", encoding="utf-8", errors="replace", closefd=False)


def enable_vt() -> None:
    """A detecção de cores só escolhe cor verdadeira se o modo VT já estiver ligado quando a interface inicia."""
    kernel32 = core._kernel32
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.SetConsoleMode.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    handle = kernel32.GetStdHandle(-11)
    mode = wintypes.DWORD()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def fail(text: str) -> int:
    print(text)
    if sys.stdin and sys.stdin.isatty():
        print("\nQualquer tecla para sair.")
        msvcrt.getwch()
    return 1


def main() -> int:
    open_console()
    enable_vt()
    parser = argparse.ArgumentParser(description=f"{core.APP}: perfis do Engine.ini do AION 2 Global (Steam)")
    parser.add_argument("--ini", help="Caminho do Engine.ini (padrão: %%LOCALAPPDATA%%\\AION2\\Saved_Steam\\Config\\Windows)")
    parser.add_argument("--profiles", help="Pasta com os perfis (padrão: pasta do programa, pasta atual, embutidos)")
    try:
        args = parser.parse_args()
    except SystemExit:
        if "__compiled__" in globals() and sys.stdin and sys.stdin.isatty():
            msvcrt.getwch()
        raise

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    ini = Path(args.ini) if args.ini else core.default_ini()
    if not ini.parent.is_dir():
        return fail(f"Pasta de configuração não encontrada:\n  {ini.parent}\n\n"
                    "Abra o AION 2 pela Steam uma vez, ou informe o caminho com --ini.")
    root = core.find_profiles_root(args.profiles)
    if root is None:
        return fail("Nenhuma pasta de perfil (1- a 5-) encontrada.")

    manager = core.Manager(ini, root)
    message = manager.ensure_original() or ""
    try:
        from astral_tui import AstralApp  # só aqui: o serviço de energia não carrega a interface
    except ImportError as error:
        return fail(f"Falta uma dependência: {error}\n\nRode: python -m pip install -r requirements.txt")
    AstralApp(manager, message).run()
    return 0


if __name__ == "__main__":
    if core.SERVICE_ARG in sys.argv[1:] and core.service_supported():
        sys.exit(core.run_power_service())
    try:
        sys.exit(main())
    except Exception as error:  # a janela fecharia sem mostrar nada ao abrir com dois cliques
        sys.exit(fail(f"Erro: {error}"))
