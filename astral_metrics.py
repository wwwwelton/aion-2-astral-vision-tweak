"""Métricas do AION 2 sem injeção: PresentData/PresentMon (frames) e Npcap (resposta de ping do jogo)."""
from __future__ import annotations

import ctypes
import os
import socket
import struct
import subprocess
import threading
import time
from collections import deque
from ctypes import wintypes
from pathlib import Path

import astral_core as core


class _Bpf(ctypes.Structure):
    _fields_ = [("length", ctypes.c_uint), ("instructions", ctypes.c_void_p)]


class _PacketHeader(ctypes.Structure):
    # timeval do Npcap no Windows usa campos de 32 bits.
    _fields_ = [("sec", ctypes.c_uint), ("usec", ctypes.c_uint),
                ("caplen", ctypes.c_uint), ("length", ctypes.c_uint)]


class _Device(ctypes.Structure):
    pass


class _Address(ctypes.Structure):
    pass


_Device._fields_ = [("next", ctypes.POINTER(_Device)), ("name", ctypes.c_char_p),
                    ("description", ctypes.c_char_p), ("addresses", ctypes.POINTER(_Address)),
                    ("flags", ctypes.c_uint)]
_Address._fields_ = [("next", ctypes.POINTER(_Address)), ("addr", ctypes.c_void_p)]


class _RapoFrame(ctypes.Structure):
    _fields_ = [("timestamp", ctypes.c_uint64), ("swap_chain", ctypes.c_uint64),
                ("lost", ctypes.c_uint32), ("reserved", ctypes.c_uint32)]


_CANCEL_CB = ctypes.CFUNCTYPE(ctypes.c_bool, ctypes.c_void_p)


def _connections() -> list[tuple[int, str, int, str, int]]:
    """Conexões TCP IPv4 estabelecidas pertencentes ao jogo, sem consultar seu processo."""
    pids = {pid for pid, name in core.list_processes() if name.lower() in core.GAME_PROCESSES}
    if not pids:
        return []
    api = ctypes.WinDLL("iphlpapi")
    api.GetExtendedTcpTable.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
                                        ctypes.c_bool, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint)
    size = ctypes.c_uint()
    api.GetExtendedTcpTable(None, ctypes.byref(size), False, 2, 5, 0)  # AF_INET, TCP_TABLE_OWNER_PID_ALL
    buffer = ctypes.create_string_buffer(size.value)
    if api.GetExtendedTcpTable(buffer, ctypes.byref(size), False, 2, 5, 0):
        return []
    count = struct.unpack_from("<I", buffer)[0]
    rows = []
    for n in range(count):
        state, local, local_port, remote, remote_port, pid = struct.unpack_from("<6I", buffer, 4 + 24 * n)
        if state == 5 and pid in pids:
            rows.append((pid, socket.inet_ntoa(struct.pack("<I", local)), socket.ntohs(local_port & 0xffff),
                         socket.inet_ntoa(struct.pack("<I", remote)), socket.ntohs(remote_port & 0xffff)))
    return rows


def _window_pids(candidates: set[int]) -> list[int]:
    """PIDs candidatos que possuem janela visível (prioriza o processo de renderização real)."""
    if not candidates:
        return []
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in candidates and pid.value not in found:
                found.append(pid.value)
        return True

    user32.EnumWindows(callback, 0)
    return found


def _game_pid() -> int | None:
    pids = [pid for pid, name in core.list_processes() if name.lower() in core.GAME_PROCESSES]
    if not pids:
        return None
    win_pids = _window_pids(set(pids))
    if win_pids:
        return win_pids[0]
    conns = _connections()
    return next((pid for pid, _, _, remote, port in conns if remote != "127.0.0.1" and port != 443), pids[0])


def _stats_from(window: list[tuple[int, int]], frequency: int) -> tuple[float, float] | None:
    """FPS e frame time da swapchain com mais apresentações na janela (mesmo método do Rintel RAPO)."""
    if frequency <= 0 or len(window) < 3:
        return None
    counts: dict[int, int] = {}
    for _, chain in window:
        counts[chain] = counts.get(chain, 0) + 1
    chain = max(counts, key=counts.__getitem__)
    times = [t for t, c in window if c == chain]
    gaps = len(times) - 1
    if gaps < 2:
        return None
    span = times[-1] - times[0]
    if span <= 0:
        return None
    seconds = span / frequency
    return gaps / seconds, 1000.0 * seconds / gaps


def _npcap(local: str):
    dll = ctypes.CDLL(str(Path(os.environ["WINDIR"]) / "System32" / "Npcap" / "wpcap.dll"))
    dll.pcap_findalldevs.argtypes = (ctypes.POINTER(ctypes.POINTER(_Device)), ctypes.c_void_p)
    dll.pcap_findalldevs.restype = ctypes.c_int
    dll.pcap_freealldevs.argtypes = (ctypes.POINTER(_Device),)
    devices = ctypes.POINTER(_Device)()
    error = ctypes.create_string_buffer(256)
    if dll.pcap_findalldevs(ctypes.byref(devices), error):
        raise OSError(error.value.decode(errors="replace"))
    try:
        current = devices
        while current:
            address = current.contents.addresses
            while address:
                raw = address.contents.addr
                if raw and ctypes.string_at(raw, 2) == b"\x02\x00" and socket.inet_ntoa(ctypes.string_at(raw + 4, 4)) == local:
                    return dll, current.contents.name
                address = address.contents.next
            current = current.contents.next
    finally:
        dll.pcap_freealldevs(devices)
    raise OSError("Adaptador Npcap do AION 2 não encontrado")


def _find_presentmon() -> Path | None:
    for candidate in (
        Path(__file__).resolve().with_name("PresentMon.exe"),
        core.app_dir() / "PresentMon.exe",
        Path.cwd() / "PresentMon.exe",
    ):
        if candidate.is_file():
            return candidate
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    cached = local / "AstralVisionBuild" / "PresentMon-2.3.1-x64.exe"
    return cached if cached.is_file() else None


def _find_capture_dll() -> Path | None:
    for name in ("presentmon_capture.bin", "presentmon_capture.dll"):
        here = Path(__file__).resolve().with_name(name)
        if here.is_file():
            return here
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    cached = local / "AstralVisionBuild" / "presentmon_capture.dll"
    return cached if cached.is_file() else None


def _has_npcap() -> bool:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    return (Path(windir) / "System32" / "Npcap" / "wpcap.dll").is_file()


def _ping_icmp(ip_str: str, timeout_ms: int = 1000) -> float | None:
    """Ping direto nativo via API iphlpapi do Windows (sem drivers nem instaladores)."""
    try:
        ip = struct.unpack("<I", socket.inet_aton(ip_str))[0]
    except (OSError, ValueError):
        return None
    try:
        api = ctypes.windll.iphlpapi
        api.IcmpCreateFile.restype = ctypes.c_void_p
        api.IcmpCloseHandle.argtypes = [ctypes.c_void_p]
        handle = api.IcmpCreateFile()
        if not handle or handle == -1 or handle == 0xFFFFFFFFFFFFFFFF:
            return None
        try:
            buf = ctypes.create_string_buffer(1024)
            if api.IcmpSendEcho(ctypes.c_void_p(handle), ctypes.c_uint32(ip), b"astral", 6, None, buf, 1024, timeout_ms) > 0:
                status = struct.unpack_from("<I", buf, 4)[0]
                if status == 0:
                    return float(struct.unpack_from("<I", buf, 8)[0])
        finally:
            api.IcmpCloseHandle(handle)
    except Exception:
        pass
    return None


def _ping_tcp(ip_str: str, port: int, timeout_s: float = 1.0) -> float | None:
    """Fallback de ping via handshake TCP se ICMP estiver bloqueado pelo servidor."""
    try:
        t0 = time.perf_counter()
        with socket.create_connection((ip_str, port), timeout=timeout_s):
            return (time.perf_counter() - t0) * 1000.0
    except OSError:
        return None

class Metrics:
    """Coleta somente enquanto a interface está aberta; não cria serviço nem entrada no logon."""

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self.frames: deque[tuple[float, float]] = deque(maxlen=1000)
        self.fps_stats: tuple[float, float, float] | None = None
        self.ping: tuple[float, float] | None = None
        self.lock = threading.Lock()
        self.process: subprocess.Popen | None = None

    def start(self) -> None:
        threading.Thread(target=self._frames, daemon=True).start()
        threading.Thread(target=self._ping, daemon=True).start()

    def stop(self) -> None:
        self.stop_event.set()
        process = self.process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()

    def values(self) -> tuple[float | None, float | None, float | None]:
        """Retorna (fps, frametime_ms, ping_ms) atuais ou None para cada métrica indisponível."""
        now = time.monotonic()
        with self.lock:
            while self.frames and now - self.frames[0][0] > 1.5:
                self.frames.popleft()
            fps: float | None = None
            frametime: float | None = None
            if self.fps_stats and now - self.fps_stats[2] < 3.0:
                fps, frametime = self.fps_stats[0], self.fps_stats[1]
            elif self.frames and now - self.frames[-1][0] < 2.5:
                durations = [value for _, value in self.frames]
                total = sum(durations)
                if total > 0:
                    fps = 1000.0 * len(durations) / total
                    frametime = total / len(durations)
            ping = self.ping[0] if self.ping and now - self.ping[1] < 20.0 else None
        return fps, frametime, ping

    def snapshot(self) -> str:
        fps, frametime, ping = self.values()
        fps_text = f"{fps:.0f}" if fps is not None else "—"
        ft_text = f"{frametime:.1f}" if frametime is not None else "—"
        ping_text = f"{ping:.0f} ms" if ping is not None else "—"
        return f"FPS {fps_text}  FRAME {ft_text} ms  PING {ping_text}"

    def _frames(self) -> None:
        dll_path = _find_capture_dll()
        exe_path = _find_presentmon()
        while not self.stop_event.is_set():
            pid = _game_pid()
            if pid is not None:
                used_native = False
                if dll_path is not None:
                    try:
                        used_native = self._capture_native_frames(dll_path, pid)
                    except OSError:
                        used_native = False
                if not used_native and exe_path is not None and exe_path.is_file():
                    self._capture_exe_frames(exe_path, pid)
            self.stop_event.wait(2)

    def _capture_native_frames(self, dll_path: Path, pid: int) -> bool:
        """Captura ETW em memória com PresentData (idêntica ao Rintel RAPO), sem processos filhos nem buffer de pipe."""
        dll = ctypes.CDLL(str(dll_path))
        dll.rapo_capture_start.argtypes = [
            ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint64), ctypes.POINTER(ctypes.c_uint64),
            ctypes.c_POINTER(ctypes.c_uint32) if hasattr(ctypes, "c_POINTER") else ctypes.POINTER(ctypes.c_uint32),
            _CANCEL_CB, ctypes.c_void_p,
        ]
        dll.rapo_capture_start.restype = ctypes.c_void_p
        dll.rapo_capture_read.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_RapoFrame), ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
        ]
        dll.rapo_capture_read.restype = ctypes.c_uint32
        dll.rapo_capture_stop.argtypes = [ctypes.c_void_p]
        dll.rapo_capture_stop.restype = None

        @_CANCEL_CB
        def is_cancelled(_ctx: int) -> bool:
            return self.stop_event.is_set()

        freq = ctypes.c_uint64()
        origin = ctypes.c_uint64()
        err = ctypes.c_uint32()
        handle = dll.rapo_capture_start(pid, ctypes.byref(freq), ctypes.byref(origin), ctypes.byref(err), is_cancelled, None)
        if not handle:
            return False
        try:
            buf = (_RapoFrame * 1024)()
            count = ctypes.c_uint32()
            window: list[tuple[int, int]] = []
            span = freq.value * 2
            while not self.stop_event.is_set():
                if dll.rapo_capture_read(handle, buf, 1024, ctypes.byref(count)) != 0:
                    break
                for i in range(count.value):
                    frame = buf[i]
                    if frame.lost == 0 and frame.timestamp >= origin.value:
                        window.append((frame.timestamp, frame.swap_chain))
                if window:
                    cutoff = window[-1][0] - span
                    window = [item for item in window if item[0] >= cutoff]
                    stats = _stats_from(window, freq.value)
                    if stats is not None:
                        with self.lock:
                            self.fps_stats = (stats[0], stats[1], time.monotonic())
                self.stop_event.wait(0.1)
            return True
        finally:
            dll.rapo_capture_stop(handle)

    def _capture_exe_frames(self, exe: Path, pid: int) -> None:
        """Fallback via PresentMon.exe sem rastreio de display e sem buffer de leitura de 8 KB."""
        try:
            self.process = subprocess.Popen(
                [str(exe), "--process_id", str(pid), "--output_stdout", "--no_console_stats",
                 "--no_track_display", "--no_track_gpu", "--no_track_input",
                 "--session_name", f"AstralVision{os.getpid()}",
                 "--stop_existing_session", "--terminate_on_proc_exit"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1, creationflags=subprocess.CREATE_NO_WINDOW)
            if self.stop_event.is_set():
                self.process.terminate()
            header: list[str] | None = None
            ms_idx = 8
            for line in iter(self.process.stdout.readline, ""):
                if self.stop_event.is_set():
                    break
                cols = [c.strip() for c in line.lstrip("\ufeff").split(",")]
                if header is None:
                    header = cols
                    if "MsBetweenPresents" in header:
                        ms_idx = header.index("MsBetweenPresents")
                    continue
                if len(cols) <= ms_idx:
                    continue
                try:
                    ms = float(cols[ms_idx])
                except ValueError:
                    continue
                if 0.1 <= ms <= 1000.0:
                    with self.lock:
                        self.frames.append((time.monotonic(), ms))
            if self.process.poll() is None:
                self.process.terminate()
            self.process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _ping(self) -> None:
        while not self.stop_event.is_set():
            conns = []
            try:
                conns = [(local, local_port, remote, port) for _, local, local_port, remote, port in _connections()
                         if remote != "127.0.0.1"]
                if conns:
                    if _has_npcap():
                        self._capture(conns)
                    else:
                        remote_ip, remote_port = conns[0][2], conns[0][3]
                        latency = _ping_icmp(remote_ip)
                        if latency is None:
                            latency = _ping_tcp(remote_ip, remote_port)
                        if latency is not None:
                            with self.lock:
                                self.ping = (latency, time.monotonic())
            except (OSError, ValueError):
                if conns:
                    remote_ip, remote_port = conns[0][2], conns[0][3]
                    latency = _ping_icmp(remote_ip)
                    if latency is None:
                        latency = _ping_tcp(remote_ip, remote_port)
                    if latency is not None:
                        with self.lock:
                            self.ping = (latency, time.monotonic())
            self.stop_event.wait(2)
    def _capture(self, conns: list[tuple[str, int, str, int]]) -> None:
        local = conns[0][0]
        conns = [c for c in conns if c[0] == local]
        dll, device = _npcap(local)
        dll.pcap_open_live.argtypes = (ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p)
        dll.pcap_open_live.restype = ctypes.c_void_p
        dll.pcap_compile.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Bpf), ctypes.c_char_p, ctypes.c_int, ctypes.c_uint)
        dll.pcap_setfilter.argtypes = (ctypes.c_void_p, ctypes.POINTER(_Bpf))
        dll.pcap_freecode.argtypes = (ctypes.POINTER(_Bpf),)
        dll.pcap_next_ex.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p))
        dll.pcap_datalink.argtypes = (ctypes.c_void_p,)
        dll.pcap_close.argtypes = (ctypes.c_void_p,)
        error = ctypes.create_string_buffer(256)
        handle = dll.pcap_open_live(device, 65535, 0, 250, error)
        if not handle:
            raise OSError(error.value.decode(errors="replace"))
        try:
            if dll.pcap_datalink(handle) != 1:  # Ethernet; não interpretar offsets de outro tipo de link.
                return
            clauses = [f"(host {remote} and port {port} and port {local_port})"
                       for _, local_port, remote, port in conns]
            program = _Bpf()
            if dll.pcap_compile(handle, ctypes.byref(program), ("tcp and (" + " or ".join(clauses) + ")").encode(), 1, 0xffffffff):
                return
            try:
                if dll.pcap_setfilter(handle, ctypes.byref(program)):
                    return
            finally:
                dll.pcap_freecode(ctypes.byref(program))
            header, data = ctypes.c_void_p(), ctypes.c_void_p()
            offset = float("inf")
            reset = time.monotonic() + 5
            seen: deque[int] = deque(maxlen=128)
            while not self.stop_event.is_set():
                if time.monotonic() >= reset:
                    if set(conns) != {(a, b, c, d) for _, a, b, c, d in _connections() if a == local and c != "127.0.0.1"}:
                        return
                    offset, reset = float("inf"), time.monotonic() + 5
                result = dll.pcap_next_ex(handle, ctypes.byref(header), ctypes.byref(data))
                if result < 0:
                    return
                if result == 0:
                    continue
                stamp = ctypes.cast(header, ctypes.POINTER(_PacketHeader)).contents
                packet = ctypes.string_at(data, stamp.caplen)
                if len(packet) < 54 or packet[12:14] != b"\x08\x00" or packet[23] != 6:
                    continue
                ip = 14 + (packet[14] & 15) * 4
                if ip + 20 > len(packet):
                    continue
                tcp = ip + (packet[ip + 12] >> 4) * 4
                if tcp > len(packet):
                    continue
                payload = packet[tcp:]
                if not payload:
                    continue
                now = time.perf_counter() * 1000
                capture_ms = stamp.sec * 1000 + stamp.usec / 1000
                offset = min(offset, now - capture_ms)
                if (socket.inet_ntoa(packet[26:30]), int.from_bytes(packet[ip:ip + 2], "big")) not in [(remote, port) for _, _, remote, port in conns]:
                    continue
                for index in range(len(payload) - 11):
                    if payload[index:index + 4] != b"\x03\x36\x00\x00":
                        continue
                    sent = struct.unpack_from("<q", payload, index + 4)[0]
                    latency = capture_ms + offset + 16_777_216_000 - sent
                    if 0 <= latency <= 3000 and sent not in seen:
                        seen.append(sent)
                        with self.lock:
                            self.ping = (latency, time.monotonic())
        finally:
            dll.pcap_close(handle)
