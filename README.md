# AION 2 Astral Vision Tweak

Instalador com interface de terminal ([Textual](https://github.com/Textualize/textual)) para aplicar os perfis do mod [Astral Vision](https://www.nexusmods.com/aion2/mods/3) no **AION 2 Global da Steam**. Ele grava o perfil e as opções escolhidas no `Engine.ini` do jogo e mantém backups para você poder voltar atrás.

## Baixar

**[Baixar o AstralVision.exe](https://github.com/wwwwelton/aion-2-astral-vision-tweak/releases/latest/download/AstralVision.exe)** (versão mais recente)

As versões anteriores estão em [Releases](https://github.com/wwwwelton/aion-2-astral-vision-tweak/releases). Não é preciso instalar Python nem baixar os perfis: tudo já está dentro do `.exe`.

## Como usar

1. **Feche o jogo.** Com o `AION2.exe` aberto, o programa bloqueia qualquer alteração no `Engine.ini`.
2. Abra o `AstralVision.exe`. Se o SmartScreen avisar, clique em **Mais informações** e depois em **Executar assim mesmo**. O aviso aparece porque o `.exe` usa um certificado autoassinado, sem reputação no Windows.
3. Na primeira execução, o programa cria o `Engine.ini.original.bak` e pergunta sobre o certificado. Veja [Assinatura](#assinatura) antes de responder; se preferir, escolha **Agora não**, pois o programa funciona do mesmo jeito.
4. Na árvore **Perfis**, à esquerda, abra o perfil, escolha a variante e pressione **Instalar**. Só um perfil fica instalado por vez: instalar outro substitui o atual.
5. Marque as opções extras que quiser na aba **Opções** e abra o jogo pela Steam.

Funciona com o mouse ou com as teclas abaixo:

| Tecla | Ação |
|---|---|
| `F1` a `F5` | Abas Opções, Energia, Backups, Assinatura e Dicas |
| `1` a `5` | Abre um perfil na árvore; setas e Enter escolhem a variante |
| `I` | Instala a variante selecionada |
| `X` | Remove o perfil e mantém as opções extras |
| `A` `E` `L` | Additions: melhorar iluminação, remover efeitos de skills e reduzir latência |
| `G` | FSR Frame Generation |
| `F` | FSR, DLSS e XeSS otimizados |
| `S` | Reduce Stutters |
| `V` | VSync desligado |
| `T` | Distance View Low: reduz a distância de desenho e de detalhe |
| `M` | Liga ou desliga o [serviço de energia](#serviço-de-energia) (só no build local) |
| `P` | Marca ou desmarca o `Engine.ini` como somente leitura |
| `U` | Desinstala tudo e restaura o `Engine.ini` original |
| `B` / `R` | Cria um backup / restaura o selecionado |
| `Ctrl+P` | Paleta de comandos, com todas as funções |
| `Q` | Sair |

### Perfis

| Perfil | Resumo |
|---|---|
| 1. Very Low | Denoisers e SSR desativados |
| 2. Default | Sombras e reflexos estáveis |
| 3. Normal | Mais sombras e AO melhor; Sharp Shadows do Astral Vision e Volumetric Clouds opcionais |
| 4. High | Nanite ativado contra pop-in em GPUs modernas; reduz o desempenho em placas antigas |
| 5. Very High | Lumen e Nanite ativados, com todas as otimizações de nitidez |

A aba **Dicas** traz as variantes, as configurações recomendadas no jogo, o que fazer se a imagem ficar nítida demais ou você perder FPS, e o link do [SCSKiller](https://github.com/BlueHeisenberg/SCSKiller), que compila os shaders antes de jogar e deixa o jogo mais fluido. Se usá-lo, não ative o gravador dele no AION 2: ele coloca uma DLL na pasta do jogo, e o próprio SCSKiller avisa que isso pode dar ban em jogos com anti-cheat.

### Opções de boot do jogo

O mod recomenda as opções abaixo, que você precisa colar manualmente em **Steam > AION 2 > Propriedades > Geral > Opções de inicialização**:

```text
-xgeshadercompile -nothreadtimeout
```

A aba **Dicas > Opções de boot do jogo** explica cada parâmetro, separado por grupo, traz um exemplo para RTX 5070 e termina com a linha pronta para copiar. Cada linha tem um botão **Copiar**.

O jogo usa a Unreal Engine 5.3.2 em build Shipping, e os parâmetros chegam ao executável, mas isso não garante que cada um tenha efeito. A [referência da Epic](https://dev.epicgames.com/documentation/en-us/unreal-engine/unreal-engine-command-line-arguments-reference) começa na versão 5.4 e descreve a engine, não o AION 2. Não encontramos uma posição oficial da NCSOFT sobre o que o anti-cheat permite: nenhum parâmetro é garantido, e o uso é por sua conta e risco.

### VSync e Distance View Low

São opções separadas e só entram no `Engine.ini` se você as marcar. Os perfis não trazem mais `foliage.MinLOD`, `foliage.OverestimateLOD` nem `r.HLOD.ForceDisableCastDynamicShadow`, e a opção de reduzir latência não traz mais `RHI.SyncInterval`: essas chaves foram movidas para cá.

- **VSync desligado** grava `r.VSync=0` e `RHI.SyncInterval=0`.
- **Distance View Low** reduz a distância de desenho e de detalhe de players, mobs, objetos, vegetação, terreno, sombras, luzes e decalques. As chaves estão em [Distance View Low.txt](Distance%20View%20Low.txt). Marcada, ela vence o View Distance Quality do jogo e faz mobs e players aparecerem mais perto. Não há confirmação de quais dessas chaves o AION 2 respeita.

### Serviço de energia

**A release publicada não traz o serviço.** O Microsoft Defender classifica como ameaça (`Behavior:Win32/Persistence.A!ml`, `Trojan:Win32/Bearfoos.A!ml`) um `.exe` novo e sem reputação que se extrai, roda sem janela e grava a inicialização automática, e o põe em quarentena. O certificado autoassinado não muda isso. O serviço só existe no [build local](#compilar) e rodando pelo script (`python -m pip install -r requirements.txt`, depois `python astral_vision.py`).

A tecla `M` liga e desliga. Ligado, o serviço roda sem janela, com o programa fechado, e inicia com o Windows:

| Situação | Plano de energia |
|---|---|
| Jogo em foco | **Desempenho Máximo**; se não existir, **Alto desempenho** |
| Jogo fora de foco | Volta ao plano que estava ativo antes |

- Os planos são mapeados em cada PC pela API do Windows, em qualquer idioma. O Desempenho Máximo costuma ser uma cópia com ID diferente em cada PC, então também é reconhecido pelo nome. Se o PC só tiver planos como Equilibrado, o menu avisa e nada muda.
- É o próprio programa rodando sem janela. Um Windows Service não enxerga qual janela está em foco, então ele fica nos aplicativos de inicialização do seu usuário e não pede administrador.
- Ele só consulta qual janela está em primeiro plano: não abre o processo do jogo nem lê a memória dele.
- Clicar em outra janela, como um overlay ou um medidor de DPS, conta como jogo fora de foco. O plano volta até você clicar no jogo.
- Se o PC desligar com o jogo em foco, o plano anterior é restaurado no próximo logon.
- Para apagar ou substituir o `.exe`, desligue o serviço antes, porque o arquivo fica em uso enquanto ele roda. Se você abrir o programa a partir de outra pasta ou de outra versão, o serviço passa a usar esse `.exe`.

Para usar o `.exe` local com o serviço, cada PC precisa liberá-lo no Defender **antes** de pressionar `M`. Isso é uma decisão sua e reduz a proteção desses caminhos: nada dentro deles será verificado. Num PowerShell aberto como administrador, ajustando o caminho do `.exe`:

```powershell
Add-MpPreference -ExclusionPath "C:\caminho\do\AstralVision.exe", "$env:LOCALAPPDATA\AstralVision\app"
```

Para desfazer, desligue o serviço com `M` e rode o mesmo comando com `Remove-MpPreference`.

## Backups e somente leitura

Os arquivos ficam em `%LOCALAPPDATA%\AION2\Saved_Steam\Config\Windows`:

| Arquivo | Conteúdo |
|---|---|
| `Engine.ini` | Configuração usada pelo jogo |
| `Engine.ini.original.bak` | Cópia feita na primeira execução, base de cada instalação |
| `Engine.ini.backup-*` | Backups criados com a tecla `B` ou automaticamente (`-auto`), quando o arquivo mudou fora do programa |
| `Engine.ini.astralvision.json` | O que está instalado |

O perfil é mesclado ao arquivo: as seções que o jogo grava, como `[Core.System]`, e a escolha de upscaler são mantidas. Outras mudanças feitas pelo jogo depois do primeiro backup não entram numa nova instalação, mas ficam salvas na cópia `-auto`.

A página do mod orienta marcar o `Engine.ini` como somente leitura, para o jogo não regravá-lo. Nesse caso o jogo também não consegue salvar mudanças de upscaler ou de Frame Generation; se isso acontecer, desmarque com a tecla `P`, mude no jogo e marque de novo.

## Assinatura

Cada release é compilada no GitHub Actions e assinada sempre com o mesmo certificado autoassinado, com carimbo de tempo da DigiCert. A DigiCert só comprova a data da assinatura; ela não emite esse certificado.

O certificado público fica dentro do `.exe`. A chave privada não vai junto: ela fica nos Secrets do repositório no GitHub e só é usada na etapa de assinatura. Como o certificado é fixo, se essa chave vazar, alguém poderá assinar outros arquivos com ela, e quem instalou o certificado confiaria neles. Nesse caso, remova-o na aba **Assinatura**.

Até você instalar o certificado, o Windows não reconhece a assinatura. Enquanto ele não estiver instalado, o programa pergunta no primeiro uso de cada versão, e a aba **Assinatura** permite instalar ou remover depois. A instalação é opcional, vale só para o seu usuário do Windows e pede confirmação. Instale apenas se você confia em quem gerou o `.exe`.

## Linha de comando

```text
AstralVision.exe [--ini CAMINHO\Engine.ini] [--profiles PASTA]
```

Se houver pastas de perfil ao lado do `.exe`, elas têm prioridade sobre as embutidas.

O build local sempre abre o próprio console, mesmo quando iniciado de um terminal. Ele se extrai em `%LOCALAPPDATA%\AstralVision\app`, e o serviço de energia guarda o estado dele em `%LOCALAPPDATA%\AstralVision`. Depois de desligar o serviço, essa pasta pode ser apagada.

Para rodar sem compilar, com o Python 3.14:

```powershell
python -m pip install -r requirements.txt
python astral_vision.py
```

## Compilar

São necessários Windows, Python 3.14, PowerShell 7 e o Visual Studio Build Tools com C++:

```powershell
./build.ps1
```

O script cria um ambiente isolado em `%LOCALAPPDATA%\AstralVisionBuild`, compila com o Nuitka e assina o `AstralVision.exe`. O build local traz o serviço de energia e usa sempre o mesmo certificado, guardado neste PC com chave não exportável e criado só se ainda não existir. Para usar outro certificado, informe `-CertThumbprint`.

Cada push na branch `main` gera automaticamente uma release `v1.0.N` pelo workflow [release.yml](.github/workflows/release.yml), com `./build.ps1 -Release`, sem o serviço. O certificado fixo das releases é gerado uma vez com `./release-cert.ps1`, que exige o GitHub CLI autenticado, grava a chave nos Secrets e o thumbprint no `build.ps1`. Sem isso, a etapa de assinatura falha e nenhuma release é publicada.

## Avisos

- Os perfis e as opções são do mod [Astral Vision](https://www.nexusmods.com/aion2/mods/3), de seu respectivo autor.
- Este projeto não é oficial nem afiliado à NCSOFT. Não encontramos uma posição oficial sobre o uso de `Engine.ini` modificado com o anti-cheat do jogo: use por sua conta e risco.
