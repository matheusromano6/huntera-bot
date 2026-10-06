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

GOLD = "#header-gold"                     # '2.044.296'

# equipamento (inventario): cada slot tem data-equip (helmet, shield...) e uma bolinha por slot de imbuement
EQUIP_SLOT = ".inventory-paperdoll .slot"
IMBUE_PIP = ".imbuement-pip"               # classe 'filled' = imbuement ativo
TOOLTIP = ".tooltip-card"                  # aparece ao passar o mouse: nome / ... / 'Basic Demon Presence (20 horas)'

# santuario de imbuements (SO' na cidade)
SHRINE_BTN = ".hud-city-actions .hud-imbue"
SHRINE_ITEM = ".imbue-item"
SHRINE_ITEM_NAME = ".imbue-item-info strong"
SHRINE_ITEM_WHERE = ".imbue-item-where"     # 'EQUIPADO'
SHRINE_SLOT = ".imbue-slot"                 # classe 'filled'; title 'Basic Demon Presence — resta 20h 0m'
SHRINE_TIER = ".imbue-tier-tab"             # Basic / Intricate / Powerful
SHRINE_LINE = ".imbue-line"                 # disabled = nivel nao permitido neste item
SHRINE_LINE_NAME = ".imbue-offer-name"
SHRINE_OFFER = ".imbue-dock-head strong"    # 'Basic Demon Presence'
SHRINE_COUNTS = ".imbue-material-counts"    # 'tem/precisa' na ordem dos materiais (com tokens: '0/2')
SHRINE_PAY = ".imbue-pay-tab"               # Sources / Tokens
SHRINE_PROTECT = ".imbue-protect input"
SHRINE_APPLY = ".imbue-apply"               # 'Imbuir — 5.000 gp'
SHRINE_REMOVE = ".imbue-remove"             # 'Remover — 15.000 gp'
SHRINE_STATUS = "#imbue-status"             # classe ok / failed
SHRINE_CLOSE = "#imbue-close"
PROMPT = ".text-prompt-dialog"
PROMPT_CONFIRM = ".text-prompt-dialog .text-prompt-confirm"
PROMPT_CANCEL = ".text-prompt-dialog .text-prompt-cancel"

# loja > leilao (compra o mais barato; o item vai pro DEPOT, e o santuario conta o depot)
STORE_NAV = "#nav-store"
TRADE_TAB = ".trade-tab"                    # 'LEILÃO'
TRADE_CLOSE = "#trade-close"
MARKET_SEARCH = "#market-search"
MARKET_ITEM = ".market-item"
MARKET_ITEM_NAME = ".market-item-name"
MARKET_SELL_ROWS = ".market-offers-block.sell tbody tr"   # vendedor/qtd/preço/total, ja do mais barato
MARKET_TAKE = "button.market-take"
MARKET_ACCEPT = ".market-accept"
MARKET_ACCEPT_LEAD = ".market-accept-lead"      # 'Comprar de <vendedor>'
MARKET_ACCEPT_TERMS = ".market-accept-terms"    # '151 de gold cada · 10 disponíveis'
MARKET_AMOUNT = ".market-accept .num-field-input"
MARKET_TOTAL = ".market-accept-total"           # 'Total: 4.998 de gold'
MARKET_CONFIRM = ".market-accept button.market-primary"
MARKET_DISMISS = ".market-accept .market-accept-dismiss"

# Bestiary (rastreador do HUD): cabecalho 'Rat Cellars 0 / 1' = criaturas TOTALMENTE concluidas
BESTIARY_HEAD = ".bestiary-tracker-hunt-head"
BESTIARY_ROW = ".bestiary-tracker-row"
BESTIARY_LABEL = ".bestiary-tracker-label"
BESTIARY_COUNT = ".bestiary-tracker-row-count"
