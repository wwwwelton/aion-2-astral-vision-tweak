"""Conteúdo das dicas do Astral Vision. Os quatro primeiros tópicos são o Readme.txt do mod, traduzido."""
from __future__ import annotations

from dataclasses import dataclass

from astral_core import ORIGINAL_BAK, STEAM_LAUNCH

BOOT_TOPIC = "Opções de boot do jogo"
DOCS_URL = "https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-command-line-arguments-reference"

TIPS = {
    "Perfis": """\
| Perfil | Resumo |
|---|---|
| Very Low | Denoisers e SSR desativados |
| Default | Sombras e reflexos estáveis |
| Normal | Mais sombras e AO melhor; Sharp Shadows do Astral Vision e Volumetric Clouds opcionais |
| High | Nanite ativado contra pop-in em GPUs modernas; reduz o desempenho em placas antigas |
| Very High | Lumen e Nanite ativados, com todas as otimizações de nitidez |
""",
    "Variantes dos perfis": """\
| Variante | O que faz |
|---|---|
| TAA | Otimizações de Temporal Anti-Aliasing; efeitos temporais minimizados |
| TSR | Otimizações de Temporal Super Resolution; nitidez máxima, sem os efeitos do TAA |
| Astral Shadows | Sombras nítidas exclusivas do Astral Vision |
| Astral Clouds | Nuvens ocultas do AION 2; grande ganho de desempenho em placas antigas |
| Volumetric Clouds | Nuvens padrão |
""",
    "Se algo não ficar bom": """\
| Problema | O que fazer |
|---|---|
| Nítido demais, prefere a suavidade padrão | No jogo: Upscaler TAA |
| Continua nítido demais | No jogo: Post-Processing Quality VeryLow |
| Sombras nítidas ou pixeladas demais | Variante Default Shadows |
| Quer as nuvens padrão de volta | Variante Volumetric Clouds |
| Perdeu FPS ou desempenho | Perfil Normal |
""",
    "Configurações no jogo": """\
| Configuração | Valor |
|---|---|
| Resolution Scale | Native |
| Effect Quality | VeryLow ou Low |
| Shadow Quality | VeryLow, Low ou Normal |
| Shading Quality | VeryLow ou Low |
| Post-Processing Quality | VeryLow (Low para mais nitidez) |
| Upscaler | TSR, FSR, DLSS ou XeSS |

Para reduzir a sensibilidade à luz: **Accessibility > Visual Assist > White Point Reduction**.
""",
    BOOT_TOPIC: "",
    "SCSKiller: compilar os shaders": """\
O SCSKiller compila os shaders antes de você jogar e deixa o jogo mais fluido. É gratuito, de código aberto e funciona \
com GPU NVIDIA ou AMD.

[github.com/BlueHeisenberg/SCSKiller](https://github.com/BlueHeisenberg/SCSKiller)

Baixe só pelas Releases desse repositório e compile com o jogo fechado.

**Não ative o gravador (recorder) no AION 2:** ele coloca uma `d3d12.dll` na pasta do jogo, e o próprio SCSKiller avisa \
que isso pode dar ban em jogos com anti-cheat e que a detecção dele pode falhar.

Não é uma ferramenta deste projeto: use por sua conta e risco.
""",
    "Somente leitura": """\
Marcado, o jogo não consegue regravar o `Engine.ini`. É o que a página do mod orienta.

Se o jogo não salvar uma mudança de upscaler ou de Frame Generation: desmarque, feche o programa, mude no jogo, feche o \
jogo e marque de novo.

O programa continua podendo instalar com o arquivo marcado, e a marca é mantida. Desinstalar tudo devolve o arquivo ao \
estado original, sem a marca.
""",
    "Serviço de energia": """\
A tecla `M`, ou a aba **Energia**, liga e desliga. Ligado, ele roda sem janela, com o programa fechado, e inicia com o \
Windows.

| Situação | Plano de energia |
|---|---|
| Jogo em foco | Desempenho Máximo; se não existir, Alto desempenho |
| Jogo fora de foco | Volta ao plano que estava ativo antes |

Os planos são mapeados em cada PC pela API do Windows, em qualquer idioma. Se o PC só tiver planos como Equilibrado, o \
programa avisa e nada muda.

Fica nos aplicativos de inicialização deste usuário e não precisa de administrador. Só consulta qual janela está em \
primeiro plano: não abre o processo do jogo nem lê a memória dele. Para apagar ou substituir o `.exe`, desligue o serviço \
antes, porque o arquivo fica em uso enquanto ele roda.

**Só existe no build local e rodando pelo script.** O Microsoft Defender bloqueia o `.exe` quando ele roda sem janela e \
grava a inicialização automática, então a release publicada não traz o serviço. Veja o README.
""",
    "VSync e Distance View Low": """\
**VSync desligado** grava `r.VSync=0` e `RHI.SyncInterval=0`. O mod trazia `RHI.SyncInterval=0` em "reduzir latência"; \
agora ele só entra com esta opção.

**Distance View Low** reduz a distância de desenho e de detalhe de players, mobs, objetos, vegetação, terreno, sombras, \
luzes e decalques. Usa os valores de Low da própria engine onde eles existem. Os perfis não trazem mais nenhuma dessas \
chaves: elas só entram com a opção marcada.

Marcada, ela vence o View Distance Quality do jogo e faz mobs e players aparecerem mais perto. Deixe desmarcada se isso \
incomoda. Não há confirmação de quais dessas chaves o AION 2 respeita.
""",
    "Ajustes para a versão Steam": """\
- **Arquivo:** `%LOCALAPPDATA%\\AION2\\Saved_Steam\\Config\\Windows\\Engine.ini`
- **Jogo:** `AION2.exe`, em `Aion2\\Binaries\\Win64`. Com ele aberto, nada no `Engine.ini` é alterado.

O perfil é mesclado: `[Core.System]` e a escolha de upscaler feita no jogo são mantidos.

O jogo traz FSR 4, e as chaves `r.FidelityFX.FSR3.*` do mod são do plugin antigo. A opção FSR / DLSS / XeSS grava também \
os nomes atuais, `r.FidelityFX.FSR.*`. `r.FidelityFX.FSR.QualityMode=0` fixa o FSR em Native AA, igual à intenção do mod.

A instalação Steam não traz DLL do XeSS: as chaves de XeSS não devem ter efeito.
""",
    "Atalhos": """\
Todas as funções também aparecem na paleta de comandos, com `Ctrl+P`.

| Tecla | Função |
|---|---|
| `1` a `5` | Abre um perfil na árvore; setas e Enter escolhem a variante |
| `I` | Instala a variante selecionada |
| `X` | Remove o perfil e mantém as opções extras |
| `U` | Desinstala tudo e restaura o `Engine.ini` original |
| `A` `E` `L` | Additions: melhorar iluminação, remover efeitos de skills, reduzir latência |
| `G` | FSR Frame Generation |
| `F` | FSR / DLSS / XeSS otimizados |
| `S` | Reduce Stutters |
| `V` | VSync desligado |
| `T` | Distance View Low |
| `M` | Serviço de energia (só no build local) |
| `B` / `R` | Cria um backup / restaura o selecionado |
| `P` | `Engine.ini` somente leitura |
| `F1` a `F5` | Abas Opções, Energia, Backups, Assinatura e Dicas |
| `C` / `D` | Abas Assinatura e Dicas |
| `Tab` | Passa para o próximo painel |
| `Q` | Sair |
""",
    "Como este programa funciona": f"""\
- Um perfil por vez: instalar outro substitui o atual.
- O primeiro uso cria `{ORIGINAL_BAK}` ao lado do `Engine.ini`.
- Cada instalação recalcula: backup original + perfil + opções extras.
- Se o arquivo mudou fora do programa, uma cópia `-auto` é salva antes de sobrescrever.
""",
    "Assinatura do .exe": """\
O `.exe` é assinado no build com um certificado autoassinado fixo, que fica dentro do próprio `.exe`. A chave privada não \
vai junto. A DigiCert só comprova a data da assinatura (carimbo de tempo); ela não emite este certificado.

Até instalar o certificado, o Windows não reconhece a assinatura. Enquanto ele não estiver instalado, o programa pergunta \
no primeiro uso de cada versão, e a aba **Assinatura** faz o mesmo depois, também para remover.

Instalar faz este usuário confiar em tudo que essa chave assinar: só instale se você confia em quem gerou o `.exe`. O \
SmartScreen ainda pode avisar, porque ele também considera a reputação.
""",
}

# Tecla da opção: o que ela faz, para o painel ao lado da lista de opções.
OPTION_HELP = {
    "A": "Ajusta gamma e cor para uma imagem com mais contraste.",
    "E": "Remove luzes e partículas dos efeitos de skills.",
    "L": "Reduz as filas de frames e a suavização de FPS, para menos latência.",
    "G": "Liga o FSR Frame Generation. Se o DLSS estiver ligado, escolha FSR como upscaler no jogo.",
    "F": "Otimiza FSR, DLSS e XeSS. Grava também os nomes atuais das chaves do FSR 4.",
    "S": "Cache de shaders, streaming e threads, para menos travadas.",
    "V": "Desliga o VSync. Sem esta opção, vale a configuração do jogo.",
    "T": ("Reduz a distância de desenho e de detalhe de players, mobs, objetos, vegetação, terreno, sombras, luzes e "
          "decalques. Vence o View Distance Quality do jogo: deixe desmarcada se mobs aparecendo de perto incomodam."),
}


@dataclass(frozen=True)
class BootGroup:
    title: str
    description: str
    line: str
    params: tuple[tuple[str, str, str], ...] = ()


BOOT_VERIFIED = (
    ("Engine", "Unreal Engine 5.3.2, build Shipping, segundo o relatório de crash do próprio jogo."),
    ("Chegam ao jogo", "Sim. O Steam já passa -saveddirsuffix=Steam, e é isso que cria a pasta Saved_Steam."),
    ("Suporte no AION 2", "Não confirmado. A lista abaixo é da engine, e um build Shipping pode ignorar parâmetros."),
    ("Anti-cheat", "A NCSOFT não publica o que é permitido ou proibido. Nenhum é garantido: use por sua conta e risco."),
    ("Documentação", "A referência da Epic começa na versão 5.4; a página da 5.3 vem vazia."),
)
BOOT_TEST_LINE = "-windowed -ResX=1280 -ResY=720"

BOOT_GROUPS = (
    BootGroup(
        "1. CPU e multithreading", "Paralelismo e gerenciamento das threads.",
        "-USEALLAVAILABLECORES -rhithread -parallelrendering -useperfthreads -AsyncLoadingThread -AsyncPostLoad",
        (
            ("-USEALLAVAILABLECORES", "Usa todos os núcleos disponíveis.", "Testar"),
            ("-rhithread", "Ativa a thread RHI. Pode ajudar ou aumentar o overhead.", "Testar sozinho"),
            ("-parallelrendering", "Ativa a renderização paralela e define r.RHICmdBypass 0.", "Testar sozinho"),
            ("-useperfthreads", "Força o uso de threads para desempenho.", "Incerto"),
            ("-AsyncLoadingThread", "Ativa o carregamento assíncrono de pacotes.", "Testar"),
            ("-AsyncPostLoad", "Ativa o pós-carregamento assíncrono de pacotes.", "Testar"),
        ),
    ),
    BootGroup(
        "2. GPU e DirectX 12", "Seleção de GPU, API gráfica e modo de exibição.",
        "-d3d12 -PreferedHighPerformance -preferNvidia -fullscreen",
        (
            ("-d3d12", "Usa DirectX 12 (igual a -dx12), a API que os arquivos do jogo trazem.", "Condicional"),
            ("-PreferedHighPerformance", "Prefere o dispositivo D3D de alto desempenho. A grafia é essa mesmo.", "Testar"),
            ("-preferNvidia", "Prefere a NVIDIA como fabricante do adaptador.", "Só NVIDIA"),
            ("-fullscreen", "Usa tela cheia. No Windows 11, compare com janela sem bordas.", "Testar"),
        ),
    ),
    BootGroup(
        "3. Shaders e cache PSO", "Compilação e armazenamento de shaders. Alguns são voltados ao desenvolvimento.",
        "-psocache -xgeshadercompile -NoRemoteShaderCompile",
        (
            ("-psocache", "Força o uso do cache de PSO. Só ajuda se houver cache compatível.", "Testar"),
            ("-xgeshadercompile", "Recomendada pelo mod; não consta na referência da Epic.", "Incerto"),
            ("-NoRemoteShaderCompile", "Desativa a compilação remota de shaders.", "Sem benefício"),
        ),
    ),
    BootGroup(
        "4. FPS e sincronização", "Desativa a sincronização vertical e solicita tela cheia.",
        "-novsync -fullscreen",
        (("-novsync", 'Define r.VSync 0. A opção "VSync desligado" faz o mesmo no Engine.ini.', "Testar"),),
    ),
    BootGroup(
        "5. Carregamento de recursos", "Os do grupo 1 que tratam de carregamento. Não garantem menos stutter.",
        "-AsyncLoadingThread -AsyncPostLoad",
    ),
    BootGroup(
        "6. Inicialização e resolução 4K", "Tela cheia em 3840 x 2160. Troque pela resolução do seu monitor.",
        "-NOSPLASH -fullscreen -ResX=3840 -ResY=2160",
        (
            ("-NOSPLASH", "Desativa a tela de apresentação.", "Opcional"),
            ("-ResX= e -ResY=", "Definem a largura e a altura.", "Opcional"),
        ),
    ),
    BootGroup(
        "7. Diagnóstico e risco", "Não recomendados para uso normal: podem reduzir a estabilidade ou o desempenho.",
        "-nothreadtimeout -NoTimeouts -NOVERIFYGC -clearPSODriverCache",
        (
            ("-nothreadtimeout", "Desativa o timeout da thread de renderização. O mod recomenda; "
                                 "travamentos deixam de ser detectados.", "Evitar"),
            ("-NoTimeouts", "Desativa os timeouts de conexão de rede.", "Não usar"),
            ("-NOVERIFYGC", "Desativa a verificação do coletor de lixo.", "Evitar"),
            ("-clearPSODriverCache", "Limpa o cache de PSO do driver; pode provocar stutter.", "Diagnóstico"),
        ),
    ),
    BootGroup(
        "8. Prejudicam o desempenho", "Só para referência. Não aplique no jogo.",
        "-NoShaderCompile -norhithread -nothreading -onethread",
        (
            ("-NoShaderCompile", "Não compila shaders.", "Não usar"),
            ("-norhithread", "Desativa a thread RHI; anula -rhithread.", "Não usar"),
            ("-nothreading", "Desativa o multithreading.", "Não usar"),
            ("-onethread", "Usa uma única thread.", "Não usar"),
            ("-high", "Não consta na referência da Epic.", "Não usar"),
        ),
    ),
    BootGroup(
        "9. Alternativa DirectX 11", "Sozinha, nunca junto com -d3d12. O Nanite dos perfis High e Very High exige DX12.",
        "-d3d11",
        (("-d3d11", "Usa DirectX 11 (igual a -dx11). Pode não funcionar no AION 2.", "Diagnóstico"),),
    ),
)

EXAMPLE_TITLE = "Exemplo: RTX 5070 + i9-14900K"
EXAMPLE_NOTE = "Experimental, sem ganho comprovado no AION 2. No próprio jogo, estas configurações têm impacto mais direto:"
EXAMPLE_SETTINGS = (
    ("NVIDIA Reflex", "On; testar Boost"),
    ("DLSS", "Quality ou Balanced"),
    ("Frame Generation", "Desligado, para menor latência em PvP"),
    ("VSync", "Off inicialmente"),
    ("Mass Combat Quality", "Baixo em batalhas grandes; se mobs só aparecem de perto, teste mais alto"),
    ("Standardize Player Appearances", "Ativar em PvP massivo, se necessário"),
    ("Shadow Quality", "Médio ou Baixo"),
    ("Global Illumination", "Médio ou Baixo"),
    ("View Distance", "Alto, preservando a visibilidade"),
    ("Texture Quality", "Alto, monitorando a VRAM"),
    ("Limite de FPS", "Um valor que o PC sustente"),
)
EXAMPLE_START_LINE = "-novsync -fullscreen -PreferedHighPerformance"
EXAMPLE_NEXT = "Depois teste -rhithread e -parallelrendering separadamente, comparando frametime e 1% low."
EXAMPLE_FULL_LINE = ("-USEALLAVAILABLECORES -rhithread -parallelrendering -useperfthreads -AsyncLoadingThread "
                     "-AsyncPostLoad -psocache -d3d12 -PreferedHighPerformance -preferNvidia -novsync -fullscreen -NOSPLASH")

MOD_LINE = STEAM_LAUNCH
ALL_NOTE = ("Sem os grupos 7, 8 e 9, que são de risco ou se anulam; sem -preferNvidia, que é só para NVIDIA; "
            "sem -NoRemoteShaderCompile, que anula -xgeshadercompile; e sem resolução fixa.")
ALL_LINE = ("-USEALLAVAILABLECORES -rhithread -parallelrendering -useperfthreads -AsyncLoadingThread -AsyncPostLoad "
            "-d3d12 -PreferedHighPerformance -psocache -xgeshadercompile -novsync -fullscreen -NOSPLASH")
