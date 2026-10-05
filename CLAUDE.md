# CLAUDE.md - huntera_bot

Contexto para quem continua este projeto (outra conversa/computador). Leia inteiro antes de mexer.

## O que e
Bot do **Huntera** (huntera.com.br, MMORPG idle de navegador) que roda **dentro do IdleDeck** (app Electron da
Microsoft Store que abre varias contas de jogos idle em "slots"). So Windows. Repo: `matheusromano6/huntera-bot`
(publico). Projeto **separado** do bot do Baiak (`matheusromano6/baiakidle`) - nao misturar versoes/releases.

O bot se conecta ao IdleDeck por **depuracao remota (CDP, porta 9224)** com Playwright; cada conta do Huntera e uma
pagina `huntera.com.br` na mesma conexao. Paginas de outros jogos do IdleDeck nunca sao tocadas.

## Estrutura (`huntera_bot/`)
- `selectors.py` - TODOS os seletores do jogo (confirmados ao vivo). Se o HTML mudar, e so aqui.
- `account.py` - uma conta: `read()` (1 evaluate -> `State`) e acoes (sair, vender, despachar, iniciar caçada, treino).
  `_click()` e o clique robusto (janelas do HUD cobrem botoes: dispara `click` direto SO' em "intercepts pointer events").
- `engine.py` - agrupa contas em times/solo, decide (stamina > capacidade > bestiary) e executa os ciclos. `Memory` (memory.json).
- `idledeck.py` (conexao/descoberta), `launcher.py` (abre o IdleDeck com a porta), `updater.py` (botao Atualizar),
  `gui.py` (CustomTkinter + bandeja), `runner.py` (thread do motor), `catalog.py` + `data/hunts.json` (75 caçadas, ordem do jogo),
  `config.py` (padroes), `paths.py` (arquivos ao lado do .exe quando empacotado).
- `tests/` (80 testes: `python -m unittest discover -s tests`). Nomes de personagens reais NAO entram nos testes/repo.

## O que o bot faz (regras)
- **Capacidade:** QUALQUER conta do time >= `capacity_pct` -> a lider sai (leva todos, 5s) -> cada conta vende a MOCHILA (marca tudo)
  -> a lider reinicia "com o time" na mesma hunt. Solo faz sozinha. Cooldown 120s ok / 600s falha.
- **Despacho** (1x/h, sem sair da hunt): quando pronto e capacidade >= `dispatch.min_cap_pct`.
- **Stamina/treino:** QUALQUER conta <= `training.stamina_minutes` (15) -> time inteiro pra cidade, cada personagem inicia o treino
  online da habilidade escolhida (`training.by_name`, senao padrao da vocacao; o jogo oferece as 6 a todos). Lembra a hunt
  em memory.json e VOLTA quando TODAS as contas treinando chegam a `resume_stamina_minutes` (600 = 10h).
- **Nunca parado na cidade (v1.2.2):** conta na cidade sem treino por > `idle_city_seconds` (90) -> se o time esta em modo treino
  (memory.json), stamina baixa ou hunt desconhecida: reinicia o treino dela; senao volta pra ultima hunt. O log avisa
  "saiu do treino" com os toasts da tela (causa de o treino cair ainda NAO descoberta - ver log do usuario de 05/10).
- **Bestiary em cadeia:** contador do cabecalho da hunt N/N em TODAS as contas QUE MOSTRAM o rastreador -> proxima da lista (config `bestiary_chain`).
- O bot SEMPRE age (nao existe modo simulacao). O usuario protege itens antes; tudo da mochila pode ser vendido.

## Fatos do jogo (confirmados ao vivo - nao redescobrir)
- Cabecalho vem em CAIXA ALTA ("MR SORC"), a party em "Nome Normal": comparar com casefold. Identidade da conta = `.header-character-name`.
- Estado: em hunt = `.hud-leave-group` visivel; cidade = `.hud-city-actions .hud-depot` visivel; `.world-loading` = "ENTERING WORLD";
  saindo = `#nav-leave-hunt` com texto "SAINDO EM nS..." (5s, sem confirmacao; nao clicar de novo).
- Capacidade: `title` de `.inventory-capacity strong` = "Carregando X de Y oz" (o texto mostra o que AINDA CABE). Max difere por personagem.
- Time: so inicia com TODOS na cidade (senao toast "nao conseguiu entrar de fora da cidade" e cancela em silencio); quem tem
  "aceitar tudo do lider" entra sozinho (convite `.party-invite`); lider sair leva todos. Em party a lider so ve "Iniciar com o time".
  Time = ligacao MUTUA na party (a lista da party pode ter membros que nao estao abertos).
- Venda rapida: so a mochila (bolsa nao aparece); marcas persistem; botao desabilitado = nada a vender. Despacho usa a mesma janela;
  em intervalo tem classe `cooling` e texto "PRONTO EM mm:ss" (o `disabled` continua falso). A seta "Vender sozinho quando..." existe
  mas fica `hidden` (provavel recurso bloqueado/Premium).
- Bestiary: o cabecalho "N / M" so conta criaturas TOTALMENTE concluidas; ao fechar uma fase a linha reinicia com alvo maior
  (2500 -> 5000) e aparece toast "Fase N do Bestiary concluida". Contagem e por conta (no time, abates contam pra todos).
- Algumas contas NAO mostram o rastreador do Bestiary (`.bestiary-tracker-hunt-head` ausente): ficam sem hunt_name/bestiary.
  A hunt do time vem de quem mostra (ou da memoria); a interface usa `snapshot["hunts"]` e `snapshot["bestiary"]` ("N/M (time)").
- Pull salvo e por conta; no time vale o da lider. Selecionar uma hunt na lista troca a tela pra detalhe (a lista some).
- Stamina: `.hud-stamina-clock` ("5:43h"); gasta caçando, recarrega fora. Treino: painel `[aria-label="Treino ativo"]` (a conta continua
  "na cidade"); o botao Cancelar pode ficar coberto pela party.
- Menus de contexto (ex: "Sair sozinho quando...") NAO fecham com Escape: clicar fora (`.context-backdrop`) ou na seta de novo.
- Avisos do jogo: `.system-toast` (inclusive rateio de custos ao sair do time e drops globais de outros jogadores - ignorar).

## IdleDeck
- Nao expoe porta sozinho: abrir pela ATIVACAO DO PACOTE com `--remote-debugging-port=9224` (ver `launcher.py`).
- **NUNCA matar os processos do IdleDeck a forca** (deixa subprocesso "fantasma": "aplicativo sendo encerrado" 0x8000001A ate reiniciar o PC).
  Fechar so por CloseMainWindow e esperar o usuario confirmar "Sair".
- `context.new_page()` NAO e suportado no IdleDeck; `bring_to_front` traria a janela do app pra frente (nao usar).
- Dois idledecks (Store e copia em C:\IdleDeck-VPN com split tunneling da VPN, porta 9225) ja foram usados pelo bot do Baiak;
  uma ideia futura e o Huntera usar a copia pra ter outro IP.

## Release (so Windows)
1. Bump em `huntera_bot/__init__.py` (VERSAO unica), testes verdes, README se preciso.
2. Build (PowerShell, na raiz): PyInstaller `--onefile --windowed --name HunteraBot` com **caminhos ABSOLUTOS** nos `--add-data`
   (driver do playwright, `huntera_bot\data`, `icon.ico`) e `--hidden-import pystray --hidden-import pystray._win32`; ver `build.bat`.
3. Zip `dist/HunteraBot-windows.zip` (nome FIXO: o atualizador procura esse asset) com `HunteraBot.exe` + `LEIA-ME.md`.
4. `git add` so de `huntera_bot tests README.md CLAUDE.md` (NUNCA `git add -A`: ja entrou arquivo temporario) e commit com
   `Co-Authored-By`. Notas da release num arquivo FORA do repo. `gh release create vX.Y.Z ... --repo matheusromano6/huntera-bot`.
5. `gh` so funciona no PowerShell neste PC; comandos longos misturando here-string e Remove-Item ja foram bloqueados: faca em passos.
- Atualizador: botao Atualizar -> checa a ultima release, baixa, troca o .exe por tarefa agendada (testado ponta a ponta contra o GitHub).

## Pendencias / ideias
- Time de 4 contas ja aparece na pratica; observar o ciclo de capacidade ao vivo (v1.2.1 corrigiu o clique coberto pelo "Ratear custos da hunt").
- Medir o ritmo de recarga da stamina em treino (10h pode demorar).
- Lista da cadeia do Bestiary (a interface existe; o usuario escolhe), e se uma conta com stamina baixa deve treinar sozinha.
- Interface: mostrar progresso do ciclo; tratar morte de personagem; Mac nao e suportado.
- Regra de ouro: so agir em paginas `huntera.com.br`; nao interferir nos outros jogos do IdleDeck.
