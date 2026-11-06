# AION 2 Astral Vision Tweak

Instalador de terminal para aplicar os perfis do mod [Astral Vision](https://www.nexusmods.com/aion2/mods/3) no **AION 2 Global da Steam**. Ele grava o perfil e as opções escolhidas no `Engine.ini` do jogo e mantém backups para você poder voltar atrás.

## Baixar

**[Baixar o AstralVision.exe](https://github.com/wwwwelton/aion-2-astral-vision-tweak/releases/latest/download/AstralVision.exe)** (versão mais recente)

As versões anteriores estão em [Releases](https://github.com/wwwwelton/aion-2-astral-vision-tweak/releases). Não é preciso instalar Python nem baixar os perfis: tudo já está dentro do `.exe`.

## Como usar

1. **Feche o jogo.** Com o `AION2.exe` aberto, o programa bloqueia qualquer alteração no `Engine.ini`.
2. Abra o `AstralVision.exe`. Se o SmartScreen avisar, clique em **Mais informações** e depois em **Executar assim mesmo**. O aviso aparece porque o `.exe` usa um certificado autoassinado, sem reputação no Windows.
3. Na primeira execução, o programa cria o `Engine.ini.original.bak` e pergunta sobre o certificado. Veja [Assinatura](#assinatura) antes de responder; se preferir, escolha **Agora não**, pois o programa funciona do mesmo jeito.
4. Pressione uma tecla de `1` a `5` para instalar um perfil e escolha a variante. Só um perfil fica instalado por vez: instalar outro substitui o atual.
5. Marque as opções extras que quiser e abra o jogo pela Steam.

Use as setas e Enter, ou as teclas abaixo:

| Tecla | Ação |
|---|---|
| `1` a `5` | Instala um perfil. Na tecla do perfil já instalado, troca a variante ou desinstala |
| `A` `E` `L` | Additions: melhorar iluminação, remover efeitos de skills e reduzir latência |
| `G` | FSR Frame Generation |
| `F` | FSR, DLSS e XeSS otimizados |
| `S` | Reduce Stutters |
| `P` | Marca ou desmarca o `Engine.ini` como somente leitura |
| `U` | Desinstala tudo e restaura o `Engine.ini` original |
| `B` / `R` | Cria um backup / restaura um backup |
| `C` | Assinatura e certificado do `.exe` |
| `D` | Dicas do mod |
| `Q` | Sair |

### Perfis

| Perfil | Resumo |
|---|---|
| 1. Very Low | Denoisers e SSR desativados |
| 2. Default | Sombras e reflexos estáveis |
| 3. Normal | Mais sombras e AO melhor; Sharp Shadows do Astral Vision e Volumetric Clouds opcionais |
| 4. High | Nanite ativado contra pop-in em GPUs modernas; reduz o desempenho em placas antigas |
| 5. Very High | Lumen e Nanite ativados, com todas as otimizações de nitidez |

O menu **Dicas** traz as variantes, as configurações recomendadas no jogo, o que fazer se a imagem ficar nítida demais ou você perder FPS, e o link do [SCSKiller](https://github.com/BlueHeisenberg/SCSKiller), que compila os shaders antes de jogar e deixa o jogo mais fluido. Se usá-lo, não ative o gravador dele no AION 2: ele coloca uma DLL na pasta do jogo, e o próprio SCSKiller avisa que isso pode dar ban em jogos com anti-cheat.

### Steam Launch Options

O mod recomenda as opções abaixo, que você precisa colar manualmente em **Steam > AION 2 > Propriedades > Geral > Opções de inicialização**:

```text
-xgeshadercompile -nothreadtimeout
```

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

Cada release é compilada no GitHub Actions e assinada com um certificado autoassinado novo, com carimbo de tempo da DigiCert. A DigiCert só comprova a data da assinatura; ela não emite esse certificado.

O certificado público fica dentro do `.exe`. A chave privada não vai junto e é descartada quando a compilação termina, então ninguém pode usá-la para assinar outros arquivos.

Até você instalar o certificado, o Windows não reconhece a assinatura. O programa pergunta no primeiro uso de cada versão, e a tecla `C` permite instalar ou remover depois. A instalação é opcional, vale só para o seu usuário do Windows e pede confirmação. Instale apenas se você confia em quem gerou o `.exe`.

## Linha de comando

```text
AstralVision.exe [--ini CAMINHO\Engine.ini] [--profiles PASTA]
```

Se houver pastas de perfil ao lado do `.exe`, elas têm prioridade sobre as embutidas.

## Compilar

São necessários Windows, Python 3.14, PowerShell 7 e o Visual Studio Build Tools com C++:

```powershell
./build.ps1
```

O script cria um ambiente isolado em `%LOCALAPPDATA%\AstralVisionBuild`, compila com o Nuitka e assina o `AstralVision.exe`. Para usar outro certificado, informe `-CertThumbprint`.

Cada push na branch `main` gera automaticamente uma release `v1.0.N` pelo workflow [release.yml](.github/workflows/release.yml).

## Avisos

- Os perfis e as opções são do mod [Astral Vision](https://www.nexusmods.com/aion2/mods/3), de seu respectivo autor.
- Este projeto não é oficial nem afiliado à NCSOFT. Não encontramos uma posição oficial sobre o uso de `Engine.ini` modificado com o anti-cheat do jogo: use por sua conta e risco.
