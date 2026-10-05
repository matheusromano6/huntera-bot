"""Seletores do Huntera, todos CONFIRMADOS ao vivo (mapeamento com 2 contas no
IdleDeck). Se o jogo mudar o HTML, e' so' aqui que se mexe."""

NAME = ".header-character-name"
VOCATION = ".header-character-vocation span"

# estado
LEAVE_GROUP = ".hud-leave-group"          # visivel so' DENTRO da hunt
CITY_MARKER = ".hud-city-actions .hud-depot"   # visivel so' na CIDADE
WORLD_LOADING = ".world-loading"          # 'ENTERING WORLD n%'
LEAVE_BTN = "#nav-leave-hunt"             # texto vira 'SAINDO EM 5S...' na contagem (5s, sem confirmacao)
TOAST = ".system-toast"

# capacidade: o 'title' traz 'Carregando X de Y oz'
CAPACITY = ".inventory-capacity strong"

# venda (cidade) e despacho (dentro da hunt) usam a MESMA janela
QUICK_SELL_BTN = ".hud-city-actions .hud-quick-sell"
DISPATCH_BTN = "#nav-hunt-quick-sell"     # classe 'cooling' + texto 'PRONTO EM mm:ss' = em intervalo (1/h)
QS_WINDOW = ".quick-sell-window"
QS_ROW = ".quick-sell-row"                # aria-pressed / classe 'marked'
QS_CONFIRM = ".quick-sell-window .quick-sell-confirm"
QS_CANCEL = ".quick-sell-window .quick-sell-cancel"

# iniciar caçada
START_NAV = "#nav-start-hunt"
ORGANIZE = "#hunt-organize"
HUNT_WINDOW = ".hunt-window"
HUNT_ENTRY = 'button.hunt-entry[aria-label="Ver detalhes de {name}"]'
HUNT_TIER = ".hunt-tier"                  # o escolhido tem a classe 'selected'
START_SOLO = "#hunt-start"                # so' existe/visivel FORA de party
START_TEAM = "#hunt-start-team"           # lider em party; todos precisam estar na cidade
HUNT_CLOSE = "#hunt-close"

# stamina da conta: 'Stamina 5:43h - gasta cacando, recarrega em qualquer outro lugar'
STAMINA = ".hud-stamina-clock"

# treino (Caçar > aba Treino)
HUNT_TAB = ".hunt-tab"
TRAIN_SKILL = ".hunt-training .train-skill"        # classe 'active' / aria-pressed = escolhida
TRAIN_MODE = ".hunt-training .train-mode"          # secoes: 'Treino online', 'Treino offline' (Premium)
TRAIN_START = ".train-start"                       # desabilitado enquanto a conta esta em caçada

# painel 'Treino ativo' (aparece enquanto a conta treina; a conta continua 'na cidade' pro jogo)
TRAINING = '[aria-label="Treino ativo"]'
TRAINING_SKILL = '[aria-label="Treino ativo"] .training-skill'
TRAINING_CANCEL = '[aria-label="Treino ativo"] button'

# party
PARTY_MEMBER = ".party-member"
PARTY_NAME = ".party-name"
PARTY_LEADER = ".party-leader"
PARTY_FOLLOW = ".party-follow"

# Bestiary (rastreador do HUD): cabecalho 'Rat Cellars 0 / 1' = criaturas TOTALMENTE concluidas
BESTIARY_HEAD = ".bestiary-tracker-hunt-head"
BESTIARY_ROW = ".bestiary-tracker-row"
BESTIARY_LABEL = ".bestiary-tracker-label"
BESTIARY_COUNT = ".bestiary-tracker-row-count"
