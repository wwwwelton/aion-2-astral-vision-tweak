"""Interface do Astral Vision, em Textual: perfis na lateral, painéis com abas à direita e atalhos no rodapé."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from rich.table import Table
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult, SystemCommand
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.theme import Theme
from textual.widgets import (
    Button,
    ContentSwitcher,
    DataTable,
    Footer,
    Markdown,
    OptionList,
    SelectionList,
    Static,
    Switch,
    TabbedContent,
    TabPane,
    Tree,
)
from textual.widgets.selection_list import Selection

import astral_core as core
from astral_tips import (
    ALL_LINE,
    ALL_NOTE,
    BOOT_GROUPS,
    BOOT_TEST_LINE,
    BOOT_TOPIC,
    BOOT_VERIFIED,
    DOCS_URL,
    EXAMPLE_FULL_LINE,
    EXAMPLE_NEXT,
    EXAMPLE_NOTE,
    EXAMPLE_SETTINGS,
    EXAMPLE_START_LINE,
    EXAMPLE_TITLE,
    MOD_LINE,
    OPTION_HELP,
    TIPS,
)

INK, MUTED = "#E2E8F0", "#8FA3BF"
TEAL, PURPLE, PINK = "#5EEAD4", "#C084FC", "#F472B6"
GREEN, YELLOW, RED = "#34D399", "#FBBF24", "#F87171"
ASTRAL_THEME = Theme(
    name="astral", primary=TEAL, secondary=PURPLE, accent=PINK, foreground=INK, background="#0B1424",
    surface="#0F1B30", panel="#16243D", success=GREEN, warning=YELLOW, error=RED, dark=True,
)
SERVICE_MISSING = "A release publicada não traz o serviço: o Microsoft Defender a bloquearia. Veja o README."


def recommendation_style(text: str) -> str:
    if text.startswith("Não usar"):
        return RED
    if text.startswith(("Evitar", "Diagnóstico")):
        return YELLOW
    if text.startswith("Testar"):
        return GREEN
    return MUTED


def params_table(params: tuple[tuple[str, str, str], ...]) -> Table:
    table = Table(box=None, expand=True, pad_edge=False, show_header=False, padding=(0, 2, 0, 0))
    table.add_column(style=TEAL, no_wrap=True, width=24)
    table.add_column(ratio=1, style=INK)
    table.add_column(no_wrap=True, width=14)
    for name, what, recommendation in params:
        table.add_row(name, what, Text(recommendation, style=recommendation_style(recommendation)))
    return table


def pairs_table(rows: tuple[tuple[str, str], ...], label_style: str) -> Table:
    table = Table(box=None, expand=True, pad_edge=False, show_header=False, padding=(0, 2, 0, 0))
    table.add_column(style=label_style, no_wrap=True)
    table.add_column(ratio=1, style=INK)
    for row in rows:
        table.add_row(*row)
    return table


def option_title(option: core.Option) -> str:
    """O rótulo das opções, sem a explicação que a Distance View Low traz depois dos dois pontos."""
    return option.label.split(":")[0] if option.key == "T" else option.label


def shorten_left(text: str, width: int) -> str:
    """Num caminho, o que importa está no final."""
    return text if len(text) <= width else "…" + text[-(width - 1):]


def describe_node(name: str, rel: str) -> str:
    if "/" not in rel:
        return core.LEVEL_INFO.get(name[0], "")
    low = name.lower()
    return next((text for key, text in core.VARIANT_INFO.items() if low.startswith(key)), "")


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "cancel", "Cancelar")]

    def __init__(self, heading: str, text: str, confirm: str, cancel: str = "Cancelar", danger: bool = False) -> None:
        super().__init__()
        self.heading = heading
        self.text = text
        self.confirm_label = confirm
        self.cancel_label = cancel
        self.danger = danger

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static(Text(self.heading, style=f"bold {TEAL}"), id="dialog-heading")
            yield Static(Text(self.text), id="dialog-text")
            with Horizontal(id="dialog-buttons"):
                yield Button(self.confirm_label, id="yes", variant="error" if self.danger else "primary")
                yield Button(self.cancel_label, id="no")

    def on_mount(self) -> None:
        self.query_one("#no" if self.danger else "#yes").focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_cancel(self) -> None:
        self.dismiss(False)


class CopyLine(Horizontal):
    """Uma linha de parâmetros, com o botão que a copia inteira."""

    def __init__(self, line: str) -> None:
        super().__init__(classes="copy-line")
        self.line = line

    def compose(self) -> ComposeResult:
        yield Static(Text(self.line, style=INK), classes="copy-text")
        yield Button("Copiar", compact=True, variant="primary", classes="copy-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        try:
            core.copy_to_clipboard(self.line)
        except OSError as error:
            self.app.say(f"Erro: {error}")
        else:
            self.app.say("Copiado. Cole em: Steam > AION 2 > Propriedades > Geral > Opções de inicialização.")


class BootOptions(VerticalScroll):
    """A dica de opções de boot: o que foi verificado, os grupos, o exemplo e a linha completa no fim."""

    def compose(self) -> ComposeResult:
        yield Static(Text("Cole em: Steam > AION 2 > Propriedades > Geral > Opções de inicialização. "
                          "Teste um grupo por vez e compare FPS médio, 1% low e stuttering.", style=INK))
        yield Static(Text("O que foi verificado", style=f"bold {TEAL}"), classes="boot-title")
        yield Static(pairs_table(BOOT_VERIFIED, PURPLE))
        yield Markdown(f"[Referência oficial da Epic]({DOCS_URL})", classes="boot-link")
        yield Static(Text("Para ver se o jogo aceita parâmetros, teste a linha abaixo. Se abrir em janela, ele leu.",
                          style=MUTED))
        yield CopyLine(BOOT_TEST_LINE)
        for group in BOOT_GROUPS:
            yield Static(Text(group.title, style=f"bold {TEAL}"), classes="boot-title")
            yield Static(Text(group.description, style=MUTED))
            if group.params:
                yield Static(params_table(group.params))
            yield CopyLine(group.line)
        yield Static(Text(EXAMPLE_TITLE, style=f"bold {PINK}"), classes="boot-title")
        yield Static(Text(EXAMPLE_NOTE, style=MUTED))
        yield Static(pairs_table(EXAMPLE_SETTINGS, PURPLE))
        yield Static(Text("Comece só com:", style=MUTED), classes="boot-label")
        yield CopyLine(EXAMPLE_START_LINE)
        yield Static(Text(EXAMPLE_NEXT, style=MUTED), classes="boot-label")
        yield Static(Text("Linha completa do exemplo:", style=MUTED), classes="boot-label")
        yield CopyLine(EXAMPLE_FULL_LINE)
        yield Static(Text("Recomendadas pelo mod (Additions.txt)", style=f"bold {TEAL}"), classes="boot-title")
        yield CopyLine(MOD_LINE)
        yield Static(Text("Todos em linha", style=f"bold {TEAL}"), classes="boot-title")
        yield Static(Text(ALL_NOTE, style=MUTED))
        yield CopyLine(ALL_LINE)


class AstralApp(App[None]):
    TITLE = core.APP
    AUTO_FOCUS = "#profiles"
    CSS = """
    Screen { background: $background; }

    #brand { height: 1; padding: 0 1; }
    #chips { height: 1; padding: 0 1; }
    .chip { width: auto; padding: 0 1; margin-right: 1; }
    .chip.ok { background: $success-muted; color: $text-success; }
    .chip.bad { background: $error; color: $background; text-style: bold; }
    .chip.warn { background: $warning-muted; color: $text-warning; }
    .chip.off { background: $panel; color: $foreground-muted; }
    #ini-path { width: 1fr; height: 1; color: $foreground-muted; text-align: right; }

    #body { height: 1fr; margin-top: 1; }
    #sidebar { width: 33%; min-width: 28; max-width: 44; height: 100%; }
    #profiles {
        height: 1fr; background: $background; padding: 0 1;
        border: round $secondary 50%; border-title-color: $secondary; border-subtitle-color: $foreground-muted;
    }
    #profiles:focus { border: round $secondary; }
    #profile-help { height: 1; padding: 0 1; color: $foreground-muted; }

    #main { width: 1fr; height: 100%; }
    #current {
        height: auto; max-height: 12; padding: 0 1;
        border: round $secondary 50%; border-title-color: $secondary;
    }
    #current-text { height: auto; }
    #current-actions { height: 1; margin-top: 1; }
    #current-actions Button { margin-right: 2; }

    #tabs { height: 1fr; }
    #tabs ContentSwitcher { height: 1fr; }
    TabPane { padding: 1 1 0 1; height: 1fr; }

    /* As dicas têm tabelas largas: enquanto a aba está aberta, ela ocupa a tela toda. */
    #body.tips-open #sidebar { display: none; }
    #body.tips-open #current { display: none; }

    #options-pane { height: 1fr; }
    #options { width: 46; height: 1fr; border: none; background: $background; }
    #option-help-box { width: 1fr; height: 1fr; padding: 0 0 0 2; border-left: tall $panel; }
    #option-help { height: auto; }

    .switch-row { height: 3; }
    .switch-row Static { width: 1fr; height: 3; content-align: left middle; padding: 0 1; }
    #plans { height: 1fr; margin-top: 1; }

    #backups { height: 1fr; }
    #backup-actions { height: 1; margin-top: 1; margin-bottom: 1; }
    #backup-actions Button { margin-right: 2; }

    #signature-text { height: auto; }
    #signature-actions { height: 1; margin-top: 1; }
    #signature-actions Button { margin-right: 2; }

    #tip-list { width: 32; height: 1fr; border: none; background: $background; padding: 0; }
    #tip-content { width: 1fr; height: 1fr; padding: 0 0 0 2; border-left: tall $panel; }
    #tip-text, #tip-boot { height: 1fr; }
    #tip-markdown { padding: 0; margin: 0; background: $background; }
    #tip-boot { padding-right: 1; }
    .boot-title { margin-top: 1; }
    .boot-label { margin-top: 1; }
    .boot-link { height: auto; margin: 0; padding: 0; background: $background; }
    .copy-line { height: auto; margin-top: 1; background: $surface; padding: 0 1; }
    .copy-text { width: 1fr; height: auto; }
    .copy-button { width: 10; margin-left: 2; }

    ConfirmScreen { align: center middle; background: $background 60%; }
    #dialog {
        width: 76; max-width: 90%; height: auto; padding: 1 2;
        background: $surface; border: round $secondary;
    }
    #dialog-text { height: auto; margin-top: 1; }
    #dialog-buttons { height: 3; margin-top: 1; align-horizontal: right; }
    #dialog-buttons Button { margin-left: 2; }
    """
    BINDINGS = [
        Binding("f1", "tab('tab-options')", "Opções"),
        Binding("f2", "tab('tab-power')", "Energia"),
        Binding("f3", "tab('tab-backups')", "Backups"),
        Binding("f4", "tab('tab-signature')", "Assinatura"),
        Binding("f5", "tab('tab-tips')", "Dicas"),
        Binding("i", "install", "Instalar"),
        Binding("u", "uninstall", "Desinstalar"),
        Binding("b", "backup", "Backup"),
        Binding("q", "quit", "Sair"),
        Binding("x", "remove_profile", show=False),
        Binding("r", "restore", show=False),
        Binding("p", "readonly", show=False),
        Binding("m", "service", show=False),
        Binding("c", "tab('tab-signature')", show=False),
        Binding("d", "tab('tab-tips')", show=False),
        *(Binding(key.lower(), f"option('{key}')", show=False) for key in "AELGFSVT"),
        *(Binding(str(number), f"level({number})", show=False) for number in range(1, 6)),
    ]

    def __init__(self, manager: core.Manager, message: str = "") -> None:
        super().__init__()
        self.mgr = manager
        self.first_message = message
        self.register_theme(ASTRAL_THEME)
        self.theme = ASTRAL_THEME.name
        self.selected_profile: str | None = None
        self.selected_is_leaf = False
        self.selected_help = ""
        self.backup_rows: list[tuple] = []
        self.plan_rows: list[tuple] = []
        self.signature: core.ExeSignature | None = None

    # -- estrutura
    def compose(self) -> ComposeResult:
        brand = Text.assemble((core.APP, f"bold {TEAL}"), ("  AION 2 Global (Steam)", MUTED))
        yield Static(brand, id="brand")
        with Horizontal(id="chips"):
            yield Static(id="chip-game", classes="chip")
            yield Static(id="chip-service", classes="chip")
            yield Static(Text(shorten_left(str(self.mgr.ini), 62)), id="ini-path")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Tree("Perfis", id="profiles")
                yield Static(id="profile-help")
            with Vertical(id="main"):
                with Vertical(id="current"):
                    yield Static(id="current-text")
                    with Horizontal(id="current-actions"):
                        yield Button("Instalar", id="install", compact=True, variant="primary", disabled=True)
                        yield Button("Remover perfil", id="remove-profile", compact=True, disabled=True)
                        yield Button("Desinstalar tudo", id="uninstall", compact=True, variant="error")
                with TabbedContent(initial="tab-options", id="tabs"):
                    with TabPane("Opções", id="tab-options"):
                        with Horizontal(id="options-pane"):
                            yield SelectionList[str](id="options")
                            with VerticalScroll(id="option-help-box"):
                                yield Static(id="option-help")
                    with TabPane("Energia", id="tab-power"):
                        with Horizontal(classes="switch-row"):
                            yield Switch(id="service-switch", disabled=not core.service_supported())
                            yield Static(id="service-text")
                        yield DataTable(id="plans", cursor_type="row", zebra_stripes=True)
                    with TabPane("Backups", id="tab-backups"):
                        yield DataTable(id="backups", cursor_type="row", zebra_stripes=True)
                        with Horizontal(id="backup-actions"):
                            yield Button("Criar backup", id="backup", compact=True, variant="primary")
                            yield Button("Restaurar selecionado", id="restore", compact=True)
                        with Horizontal(classes="switch-row"):
                            yield Switch(id="readonly-switch")
                            yield Static(Text("Engine.ini somente leitura: o jogo não consegue regravá-lo"))
                    with TabPane("Assinatura", id="tab-signature"):
                        yield Static(id="signature-text")
                        with Horizontal(id="signature-actions"):
                            yield Button("Instalar certificado", id="cert-install", compact=True, variant="primary")
                            yield Button("Remover certificado", id="cert-remove", compact=True, variant="error")
                    with TabPane("Dicas", id="tab-tips"):
                        with Horizontal():
                            yield OptionList(*TIPS, id="tip-list")
                            with ContentSwitcher(initial="tip-text", id="tip-content"):
                                with VerticalScroll(id="tip-text"):
                                    yield Markdown(id="tip-markdown")
                                yield BootOptions(id="tip-boot")
        yield Footer()

    def on_mount(self) -> None:
        profiles = self.query_one("#profiles")
        profiles.border_title = "Perfis"
        profiles.border_subtitle = "1 a 5 abrem | Enter escolhe"
        self.query_one("#current").border_title = "Instalação"
        self.build_tree()
        self.build_options()
        plans = self.query_one("#plans", DataTable)
        plans.add_columns("Plano", "ID neste PC", "Papel")
        backups = self.query_one("#backups", DataTable)
        backups.add_columns("Arquivo", "Data", "Tamanho")
        tips = self.query_one("#tip-list", OptionList)
        tips.highlighted = 0
        self.refresh_all()
        self.set_interval(2, self.refresh_status)
        self.call_after_refresh(self.show_installed)
        if self.first_message:
            self.say(self.first_message)
        self.startup()

    @work(thread=True, exclusive=True, group="startup")
    def startup(self) -> None:
        """Sem travar a tela: acerta o serviço, limpa extrações antigas e faz a pergunta do primeiro uso."""
        try:
            if core.service_supported():
                core.sync_service()
                core.clean_old_unpacked()
        except OSError as error:
            self.call_from_thread(self.say, f"Erro no serviço de energia: {error}")
        self.call_from_thread(self.refresh_all)
        exe = core.own_exe()
        if exe is None:
            return
        try:
            build = core.sha256(exe)
            if self.mgr.state["sign_asked"] != build:
                self.call_from_thread(self.first_run_signature, exe, build, core.read_signature(exe))
        except OSError as error:  # a pergunta fica pendente para a próxima execução
            self.call_from_thread(self.say, f"Erro: {error}")

    # -- mensagens e ações
    def say(self, message: str, severity: str | None = None) -> None:
        if not message:
            return
        if severity is None:
            warning = message.startswith("Bloqueado") or "Atenção" in message
            severity = "error" if message.startswith("Erro") else "warning" if warning else "information"
        self.notify(message, severity=severity, timeout=9, markup=False)

    def attempt(self, action) -> None:
        """Roda uma ação do núcleo, mostra o resultado e alinha a tela com o estado real."""
        try:
            self.say(action())
        except core.GameRunning as error:
            self.say(str(error), "warning")
        except OSError as error:
            self.say(f"Erro: {error}")
        self.refresh_all()

    def action_tab(self, pane: str) -> None:
        self.query_one("#tabs", TabbedContent).active = pane

    def action_install(self) -> None:
        if not self.selected_is_leaf or not self.selected_profile:
            self.say("Escolha um perfil até a última variante, na árvore à esquerda.", "warning")
            return
        rel = self.selected_profile
        self.attempt(lambda: self.mgr.apply(rel, list(self.mgr.state["options"])))

    def action_remove_profile(self) -> None:
        profile = self.mgr.state["profile"]
        if not profile:
            self.say("Nenhum perfil instalado.", "warning")
            return

        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.attempt(lambda: self.mgr.apply(None, list(self.mgr.state["options"])))

        self.push_screen(ConfirmScreen("Remover o perfil", f"Remover {core.pretty_profile(profile)} e manter as opções "
                                       "extras marcadas?", "Remover perfil", danger=True), answered)

    def action_uninstall(self) -> None:
        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.attempt(self.mgr.uninstall)

        self.push_screen(ConfirmScreen("Desinstalar tudo", "Restaurar o Engine.ini original e remover o perfil e as "
                                       "opções extras?", "Sim, restaurar", danger=True), answered)

    def action_backup(self) -> None:
        def backup() -> str:
            made = self.mgr.backup_now()
            return f"Backup criado: {made.name}" if made else "Engine.ini não existe: nada a copiar."

        self.attempt(backup)

    def action_restore(self) -> None:
        self.action_tab("tab-backups")
        table = self.query_one("#backups", DataTable)
        if not self.backup_rows or table.cursor_row >= len(self.backup_rows):
            self.say("Nenhum backup encontrado.", "warning")
            return
        path: Path = self.backup_rows[table.cursor_row][0]

        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.attempt(lambda: self.mgr.restore(path))

        self.push_screen(ConfirmScreen("Restaurar backup", f"Substituir o Engine.ini atual por {path.name}?",
                                       "Restaurar"), answered)

    def action_readonly(self) -> None:
        self.attempt(self.mgr.toggle_readonly)

    def action_option(self, key: str) -> None:
        options = list(self.mgr.state["options"])
        options.remove(key) if key in options else options.append(key)
        self.attempt(lambda: self.mgr.apply(self.mgr.state["profile"], options))

    def action_level(self, number: int) -> None:
        if self.query_one("#tabs", TabbedContent).active == "tab-tips":
            self.action_tab("tab-options")  # a árvore fica escondida enquanto as dicas estão abertas
        tree = self.query_one("#profiles", Tree)
        node = next((node for node in tree.root.children if str(node.data).startswith(f"{number}-")), None)
        if node:
            tree.focus()
            node.expand()
            tree.move_cursor(node)
            self.show_selected(node)  # sem evento se o cursor já estava nessa linha

    def action_service(self) -> None:
        if not core.service_supported():
            self.say(SERVICE_MISSING, "warning")
            return
        self.query_one("#service-switch", Switch).toggle()

    @on(Button.Pressed, "#install")
    def install_pressed(self) -> None:
        self.action_install()

    @on(Button.Pressed, "#remove-profile")
    def remove_profile_pressed(self) -> None:
        self.action_remove_profile()

    @on(Button.Pressed, "#uninstall")
    def uninstall_pressed(self) -> None:
        self.action_uninstall()

    def get_system_commands(self, screen):
        """A paleta (Ctrl+P) lista todas as funções, inclusive as que só têm atalho."""
        yield from super().get_system_commands(screen)
        for title, help_text, action in (
            ("Instalar a variante selecionada", "I", self.action_install),
            ("Remover o perfil e manter as opções", "X", self.action_remove_profile),
            ("Desinstalar tudo", "U: restaura o Engine.ini original", self.action_uninstall),
            ("Criar backup", "B", self.action_backup),
            ("Restaurar o backup selecionado", "R", self.action_restore),
            ("Engine.ini somente leitura", "P: marca ou desmarca", self.action_readonly),
            ("Abrir as opções extras", "F1", lambda: self.action_tab("tab-options")),
            ("Abrir a energia e os planos deste PC", "F2", lambda: self.action_tab("tab-power")),
            ("Abrir os backups", "F3", lambda: self.action_tab("tab-backups")),
            ("Abrir a assinatura e o certificado", "F4 ou C", lambda: self.action_tab("tab-signature")),
            ("Abrir as dicas e as opções de boot do jogo", "F5 ou D", lambda: self.action_tab("tab-tips")),
        ):
            yield SystemCommand(title, f"Atalho: {help_text}", action)
        if core.service_supported():
            yield SystemCommand("Ligar ou desligar o serviço de energia", "Atalho: M", self.action_service)
        for option in self.mgr.options:
            yield SystemCommand(f"Ligar ou desligar: {option_title(option)}", f"Atalho: {option.key}",
                                lambda key=option.key: self.action_option(key))

    @on(Button.Pressed, "#backup")
    def backup_pressed(self) -> None:
        self.action_backup()

    @on(Button.Pressed, "#restore")
    def restore_pressed(self) -> None:
        self.action_restore()

    # -- perfis
    def build_tree(self) -> None:
        tree = self.query_one("#profiles", Tree)
        tree.show_root = False
        tree.guide_depth = 2
        tree.root.expand()

        def add_children(parent, folder: Path) -> None:
            for kid in core.subdirs(folder):
                rel = kid.relative_to(self.mgr.root).as_posix()
                if core.find_engine_ini(kid):
                    parent.add_leaf(kid.name, data=rel)
                else:
                    add_children(parent.add(kid.name, data=rel), kid)

        for level in core.level_dirs(self.mgr.root):
            add_children(tree.root.add(level.name, data=level.name), level)

    def all_nodes(self):
        stack = list(self.query_one("#profiles", Tree).root.children)
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            yield node

    def mark_installed(self) -> None:
        """O caminho do perfil instalado fica em verde na árvore."""
        profile = self.mgr.state["profile"] or ""
        for node in self.all_nodes():
            rel = str(node.data)
            name = rel.rsplit("/", 1)[-1]
            if profile == rel or profile.startswith(rel + "/"):
                node.set_label(Text.assemble(("● ", GREEN), (name, f"bold {GREEN}")))
            else:
                node.set_label(Text(name, style=INK))

    def show_installed(self) -> None:
        tree = self.query_one("#profiles", Tree)
        profile = self.mgr.state["profile"]
        target = next((node for node in self.all_nodes() if node.data == profile), None)
        if target is None:
            first = tree.root.children[0] if tree.root.children else None
            if first:
                tree.move_cursor(first)
                self.show_selected(first)
            return
        parent = target.parent
        while parent is not None:
            parent.expand()
            parent = parent.parent
        self.call_after_refresh(tree.move_cursor, target)

    def show_selected(self, node) -> None:
        rel = str(node.data)
        self.selected_profile = rel
        self.selected_is_leaf = not node.allow_expand
        self.selected_help = describe_node(rel.rsplit("/", 1)[-1], rel)
        self.refresh_current()

    @on(Tree.NodeHighlighted, "#profiles")
    def profile_highlighted(self, event: Tree.NodeHighlighted) -> None:
        self.show_selected(event.node)

    @on(Tree.NodeSelected, "#profiles")
    def profile_selected(self, event: Tree.NodeSelected) -> None:
        if not event.node.allow_expand:
            self.query_one("#install", Button).focus()

    # -- opções
    def build_options(self) -> None:
        selection = self.query_one("#options", SelectionList)
        active = self.mgr.state["options"]
        for option in self.mgr.options:
            prompt = Text.assemble((f"{option.key}  ", TEAL), (option_title(option), INK))
            selection.add_option(Selection(prompt, option.key, option.key in active))
        if self.mgr.options:
            selection.highlighted = 0

    @on(SelectionList.SelectionToggled, "#options")
    def option_toggled(self, event: SelectionList.SelectionToggled) -> None:
        self.action_option(event.selection.value)

    @on(SelectionList.SelectionHighlighted, "#options")
    def option_highlighted(self, event: SelectionList.SelectionHighlighted) -> None:
        self.show_option_help(event.selection.value)

    def show_option_help(self, key: str) -> None:
        option = next((option for option in self.mgr.options if option.key == key), None)
        if option is None:
            return
        keys = [*option.main_lines, *(line for lines in option.extra.values() for line in lines)]
        text = Text()
        text.append(option.label + "\n", style=f"bold {TEAL}")
        text.append(OPTION_HELP.get(key, "") + "\n\n", style=INK)
        text.append(f"Grava {len(keys)} chaves:\n", style=MUTED)
        text.append("\n".join(keys), style=MUTED)
        self.query_one("#option-help", Static).update(text)

    # -- atualização da tela
    def refresh_all(self) -> None:
        self.refresh_status()
        self.mark_installed()
        self.refresh_options()
        self.refresh_backups()
        self.refresh_power()
        self.refresh_readonly()

    def refresh_status(self) -> None:
        game = self.query_one("#chip-game", Static)
        game.remove_class("ok", "bad", "warn", "off")
        try:
            name = core.running_game_process()
        except OSError:
            game.update(Text("JOGO não verificado: alterações bloqueadas"))
            game.add_class("warn")
        else:
            game.update(Text(f"JOGO ABERTO ({name}): alterações bloqueadas" if name else "JOGO fechado"))
            game.add_class("bad" if name else "ok")
        chip = self.query_one("#chip-service", Static)
        chip.remove_class("ok", "bad", "warn", "off")
        if not core.service_supported():
            chip.update(Text("ENERGIA só no build local"))
            chip.add_class("off")
        elif not core.registered_service():
            chip.update(Text("ENERGIA desligado"))
            chip.add_class("off")
        elif core.service_running():
            chip.update(Text("ENERGIA ligado"))
            chip.add_class("ok")
        else:
            chip.update(Text("ENERGIA ligado, mas parado"))
            chip.add_class("warn")
        self.refresh_current()
        if self.query_one("#tabs", TabbedContent).active == "tab-power":
            self.refresh_power()

    def refresh_current(self) -> None:
        state = self.mgr.state
        active = [option_title(option) for option in self.mgr.options if option.key in state["options"]]
        table = Table(box=None, expand=True, pad_edge=False, show_header=False, padding=(0, 2, 0, 0))
        table.add_column(style=MUTED, no_wrap=True)
        table.add_column(ratio=1)
        table.add_row("Instalado", Text(core.pretty_profile(state["profile"]), style=GREEN if state["profile"] else MUTED))
        table.add_row("Opções", Text(", ".join(active) or "nenhuma", style=INK if active else MUTED))
        if self.selected_profile:
            chosen = Text(core.pretty_profile(self.selected_profile), style=TEAL)
            if self.selected_help:
                chosen.append(f"\n{self.selected_help}", style=MUTED)
        else:
            chosen = Text("nenhum perfil", style=MUTED)
        table.add_row("Na árvore", chosen)
        if self.mgr.changed_outside:
            table.add_row(Text("Aviso", style=YELLOW), Text("O Engine.ini mudou fora do programa (o jogo pode tê-lo "
                                                            "regravado). Reaplique se preciso.", style=YELLOW))
        for problem in self.mgr.problems:
            table.add_row(Text("Aviso", style=YELLOW), Text(problem, style=YELLOW))
        self.query_one("#current-text", Static).update(table)
        self.query_one("#install", Button).disabled = not self.selected_is_leaf
        self.query_one("#remove-profile", Button).disabled = not state["profile"]
        source = "embutidos no programa" if self.mgr.root == core.embedded_root() else self.mgr.root.name
        self.query_one("#profile-help", Static).update(Text(shorten_left(f"Perfis: {source}", 38), style=MUTED))

    def refresh_options(self) -> None:
        selection = self.query_one("#options", SelectionList)
        wanted = set(self.mgr.state["options"])
        if set(selection.selected) == wanted:
            return
        with selection.prevent(SelectionList.SelectedChanged, SelectionList.SelectionToggled):
            selection.deselect_all()
            for key in wanted:
                selection.select(key)

    def refresh_readonly(self) -> None:
        switch = self.query_one("#readonly-switch", Switch)
        with switch.prevent(Switch.Changed):
            switch.value = self.mgr.readonly

    def refresh_backups(self) -> None:
        rows = []
        for path in self.mgr.list_backups():
            info = path.stat()
            name = path.name + ("  ORIGINAL" if path == self.mgr.original else "")
            rows.append((path, name, datetime.fromtimestamp(info.st_mtime).strftime("%d/%m/%Y %H:%M"),
                         f"{info.st_size / 1024:.0f} KB"))
        if rows == self.backup_rows:
            return
        self.backup_rows = rows
        table = self.query_one("#backups", DataTable)
        table.clear()
        for row in rows:
            table.add_row(*(Text(cell) for cell in row[1:]))

    def refresh_power(self) -> None:
        supported = core.service_supported()
        registered = bool(core.registered_service()) if supported else False
        switch = self.query_one("#service-switch", Switch)
        with switch.prevent(Switch.Changed):
            switch.value = registered
        text = Text()
        if not supported:
            text.append(SERVICE_MISSING, style=YELLOW)
        else:
            try:
                label = core.boost_label()
            except OSError:
                label = "alto desempenho"
            text.append(f"Serviço de energia: {label} com o jogo em foco, sem o programa aberto", style=INK)
            problem = core.read_service_state().get("error") if registered else None
            if problem:
                text.append(f"\n{problem}", style=YELLOW)
        self.query_one("#service-text", Static).update(text)
        try:
            plans, boost, active = core.list_plans(), core.boost_plan(), core.active_plan()
        except OSError as error:
            self.query_one("#service-text", Static).update(Text(f"Erro ao mapear os planos: {error}", style=RED))
            return
        rows = []
        for plan in plans:
            roles = []
            if boost and plan.guid == boost.guid:
                roles.append("em foco")
            if plan.guid == active:
                roles.append("ativo")
            rows.append((plan.name, plan.guid, ", ".join(roles)))
        if rows == self.plan_rows:
            return
        self.plan_rows = rows
        table = self.query_one("#plans", DataTable)
        table.clear()
        for name, guid, role in rows:
            table.add_row(Text(name), Text(guid, style=MUTED), Text(role, style=GREEN))

    @on(TabbedContent.TabActivated, "#tabs")
    def tab_activated(self, event: TabbedContent.TabActivated) -> None:
        body = self.query_one("#body")
        tips_open = event.pane.id == "tab-tips"
        if tips_open != body.has_class("tips-open"):
            body.set_class(tips_open, "tips-open")
            self.query_one("#tip-list" if tips_open else "#profiles").focus()
        if event.pane.id == "tab-signature":
            self.load_signature()
        elif event.pane.id == "tab-power":
            self.refresh_power()
        elif event.pane.id == "tab-backups":
            self.refresh_backups()

    # -- energia e somente leitura
    @on(Switch.Changed, "#service-switch")
    def service_switched(self, event: Switch.Changed) -> None:
        if core.service_supported() and event.value != bool(core.registered_service()):
            event.switch.disabled = True
            self.toggle_service()

    @work(thread=True, exclusive=True, group="service")
    def toggle_service(self) -> None:
        try:
            message = core.toggle_power_service()
        except OSError as error:
            message = f"Erro: {error}"
        self.call_from_thread(self.service_toggled, message)

    def service_toggled(self, message: str) -> None:
        self.query_one("#service-switch", Switch).disabled = False
        self.say(message)
        self.refresh_all()

    @on(Switch.Changed, "#readonly-switch")
    def readonly_switched(self, event: Switch.Changed) -> None:
        if event.value != self.mgr.readonly:
            self.action_readonly()

    # -- dicas
    @on(OptionList.OptionHighlighted, "#tip-list")
    def tip_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        title = list(TIPS)[event.option_index]
        switcher = self.query_one("#tip-content", ContentSwitcher)
        if title == BOOT_TOPIC:
            switcher.current = "tip-boot"
        else:
            switcher.current = "tip-text"
            self.query_one("#tip-markdown", Markdown).update(f"## {title}\n\n{TIPS[title]}")
            self.query_one("#tip-text", VerticalScroll).scroll_home(animate=False)

    # -- assinatura
    @work(thread=True, exclusive=True, group="signature")
    def load_signature(self) -> None:
        exe = core.own_exe()
        if exe is None:
            self.call_from_thread(self.show_signature, None, None, "")
            return
        try:
            self.call_from_thread(self.show_signature, exe, core.read_signature(exe), "")
        except OSError as error:
            self.call_from_thread(self.show_signature, exe, None, str(error))

    def show_signature(self, exe: Path | None, signature: core.ExeSignature | None, problem: str) -> None:
        self.signature = signature
        text = Text()
        if exe is None:
            text.append("Rodando pelo script: não há .exe para assinar.", style=MUTED)
        elif signature is None:
            text.append(f"Erro: {problem}", style=RED)
        else:
            text.append("Assinante        ", style=MUTED)
            text.append(signature.subject + "\n", style=INK)
            text.append("Carimbo DigiCert ", style=MUTED)
            text.append(("sim" if signature.timestamped else "não") + "\n\n", style=INK)
            if signature.status == "Valid":
                text.append("O Windows já reconhece esta assinatura neste usuário.", style=GREEN)
            elif signature.status == "NotSigned":
                text.append("Este .exe não tem assinatura. Gere um assinado com o build.ps1.", style=YELLOW)
            elif signature.status == "HashMismatch":
                text.append("O .exe foi alterado depois de assinado. Não instale este certificado.", style=RED)
            else:
                text.append("O certificado autoassinado está dentro do .exe. Como não é emitido por uma autoridade, o "
                            "Windows só reconhece a assinatura depois que ele é instalado neste usuário.", style=INK)
        self.query_one("#signature-text", Static).update(text)
        status = signature.status if signature else ""
        self.query_one("#cert-install", Button).display = bool(signature) and status not in (
            "Valid", "NotSigned", "HashMismatch")
        self.query_one("#cert-remove", Button).display = status == "Valid"

    def first_run_signature(self, exe: Path, build: str, signature: core.ExeSignature) -> None:
        self.mgr.state["sign_asked"] = build
        self.mgr.save_state()
        if signature.status == "Valid":
            return
        if signature.status == "NotSigned":
            self.say("Este .exe não tem assinatura. Gere um assinado com o build.ps1.")
        elif signature.status == "HashMismatch":
            self.say("Erro: o .exe foi alterado depois de assinado. Não instale este certificado.")
        else:
            self.confirm_trust(exe, signature, first_run=True)

    def confirm_trust(self, exe: Path, signature: core.ExeSignature, first_run: bool = False) -> None:
        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.say("Aguardando o Windows: confirme a janela de segurança, se ela aparecer.")
                self.change_certificate(exe, "install")
            elif first_run:
                self.say("Certificado não instalado. Use a aba Assinatura quando quiser.")

        heading = "Primeira execução: assinatura do .exe" if first_run else "Instalar o certificado"
        text = (f"Assinante: {signature.subject}\n"
                f"Carimbo de tempo da DigiCert: {'sim' if signature.timestamped else 'não'}\n\n"
                "O certificado autoassinado está dentro do .exe. Como não é emitido por uma autoridade, o Windows só "
                "reconhece a assinatura depois que ele é instalado neste usuário.\n\n"
                "Instalar faz este usuário confiar em tudo que essa chave assinar: só instale se você confia em quem "
                "gerou o .exe.")
        self.push_screen(ConfirmScreen(heading, text, "Instalar o certificado", "Agora não"), answered)

    @on(Button.Pressed, "#cert-install")
    def cert_install_pressed(self) -> None:
        exe = core.own_exe()
        if exe and self.signature:
            self.confirm_trust(exe, self.signature)

    @on(Button.Pressed, "#cert-remove")
    def cert_remove_pressed(self) -> None:
        exe = core.own_exe()
        if exe is None:
            return

        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.change_certificate(exe, "remove")

        self.push_screen(ConfirmScreen("Remover o certificado", "O .exe continua assinado, mas o Windows deixa de "
                                       "reconhecer a assinatura neste usuário.", "Remover", danger=True), answered)

    @work(thread=True, exclusive=True, group="signature-change")
    def change_certificate(self, exe: Path, action: str) -> None:
        try:
            core.change_trust(exe, action)
            status = core.read_signature(exe).status
        except OSError as error:
            message = f"Erro: {error}"
        else:
            if action == "remove":
                message = "Certificado removido. O .exe continua assinado, mas o Windows não reconhece mais a assinatura."
            elif status == "Valid":
                message = "Certificado instalado: o Windows reconhece a assinatura do .exe."
            else:
                message = f"Certificado instalado, mas a assinatura continua como {status}."
        self.call_from_thread(self.say, message)
        self.load_signature()
