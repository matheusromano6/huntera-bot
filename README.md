# huntera_bot

Bot do Huntera (huntera.com.br) para rodar **dentro do IdleDeck**. Projeto separado do bot do Baiak.

## Interface

```
pip install -r requirements.txt
python -m huntera_bot.gui          # ou duplo clique em huntera_bot.pyw
```

Abas: **Contas** (estado ao vivo, time/solo), **Regras** (capacidade, despacho, pausas), **Bestiary** (catalogo das 75 caçadas
na ordem de progressao do jogo; escolhe, ordena e define o pull de cada uma), **Log**. X pergunta se fecha ou guarda na bandeja; minimizar vai pra bandeja.

## Linha de comando

1. Abra o IdleDeck com a depuracao remota ligada (o bot do Baiak, perfil "IdleDeck", abre o app assim; porta padrao
   `9224`) e deixe as contas do Huntera abertas.
2. Ver o estado das contas, sem fazer nada no jogo:
   ```
   python -m huntera_bot --status
   ```
3. Rodar o bot (age sozinho: sai da caçada, vende a mochila e volta):
   ```
   python -m huntera_bot
   ```

Logs em `logs/huntera_AAAA-MM-DD.log`. Testes: `python -m unittest discover -s tests`.

## O que ele faz

| Rotina | Quando | O que faz |
|---|---|---|
| Capacidade | **qualquer** conta do time chega em `capacity_pct` (90%) | a lider sai (leva o time), cada conta vende a mochila, a lider reinicia "com o time" na mesma hunt. Conta sem party faz sozinha |
| Despacho | despacho pronto (1x/hora) e capacidade >= `dispatch.min_cap_pct` | "Despachar loot" sem sair da hunt |
| Stamina / treino | **qualquer** conta do time com <= `training.stamina_minutes` (0:15h) | o time vai pra cidade e cada conta inicia o treino online da sua vocacao (Knight axe, Paladin distance, Druid/Sorcerer magic level); lembra a hunt em `memory.json` |
| Volta do treino | **todas** as contas treinando com stamina >= `training.resume_stamina_minutes` (600 = 10h) | cancela o treino de todas e a lider reinicia a hunt lembrada (com o time) |
| Bestiary em cadeia | cabecalho do rastreador fecha N/N em **todas** as contas e `bestiary_chain.enabled` | vai pra proxima hunt da lista |

Regras de seguranca: so age quando todas as contas do time estao em hunt (nunca durante carregamento ou contagem de saida),
vende **so a mochila** (a bolsa nao aparece na venda rapida), espera cooldown depois de cada ciclo (120s ok / 600s falha),
nunca toca em paginas de outros jogos do IdleDeck.

## config.json (criado na 1a execucao)

- `capacity_pct`, `dispatch`, `sell.keep` (itens que nunca marca), `hunt_tiers` (pull por hunt; vazio = usa o ultimo salvo).
- `bestiary_chain.hunts`: ex. `[{"name": "Rat Cellars"}, {"name": "Spider Nest", "tier": "Ousado"}]`.

## Estrutura

- `huntera_bot/selectors.py` - todos os seletores do jogo (confirmados ao vivo). Se o HTML mudar, e so aqui.
- `huntera_bot/account.py` - uma conta (pagina): leitura de estado e acoes.
- `huntera_bot/engine.py` - times, decisao e ciclos.
- `huntera_bot/idledeck.py` - conexao e descoberta das paginas.

## Fatos do jogo que o bot assume (mapeados ao vivo)

- Time so inicia com **todos na cidade**; quem "aceita tudo do lider" entra sozinho; a lider sair leva todos (5s).
- Em party a lider so ve "Iniciar com o time" (nao o solo).
- Bestiary: ao completar a fase a linha reinicia com alvo maior (2500 -> 5000); o cabecalho "N / M" da hunt so conta
  criaturas totalmente concluidas.
- Treino: o painel `[aria-label="Treino ativo"]` aparece (a conta continua 'na cidade' pro jogo); o botao Cancelar pode
  ficar coberto pela janela da party (o bot clica direto no botao).
- Despacho: 1x por hora; botao com classe `cooling` esta em intervalo (o `disabled` continua falso).

## Windows (executavel)

Baixe `HunteraBot-windows.zip` na pagina de releases, extraia numa pasta e abra `HunteraBot.exe`. O `config.json`,
o `memory.json` e os `logs` ficam ao lado do .exe. Para gerar o executavel: `build.bat` (precisa de `pip install pyinstaller`).
Apenas Windows.
