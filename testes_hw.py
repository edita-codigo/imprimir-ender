"""Testes das PECAS da impressora (comunicacao, termistores, aquecimento, fins de curso, motores, ventoinha, extrusor, sensor de filamento, display, CR Touch, cartao SD).
Cada teste manda G-code pela serial (a impressora tem que estar PARADA) e devolve (estado, detalhe):
  'ok' | 'falha' | 'aviso' | 'observar' (o programa fez a acao; um HUMANO confirma olhando/ouvindo)
Os testes que AQUECEM, MEXEM ou ESTICAM filamento so rodam se voce permitir. No fim, o bico, a mesa e a ventoinha sempre sao desligados."""
import re, time

# categoria: leitura (so le), aquece, mexe, extrusor
TESTES = [
    dict(id='comunicacao', nome='Comunicação e firmware', cat='leitura', desc='Pergunta ao firmware quem ele é (M115).'),
    dict(id='termistores', nome='Termistores (bico e mesa)', cat='leitura', desc='Lê as temperaturas: têm que estar numa faixa de ambiente coerente (sem fio solto/curto).'),
    dict(id='fins_de_curso', nome='Fins de curso (X, Y, Z)', cat='leitura', desc='Lê o estado dos fins de curso (M119).'),
    dict(id='sensor_filamento', nome='Sensor de filamento', cat='leitura', desc='Lê se o sensor de fim de filamento está ligado e o que ele vê agora.'),
    dict(id='cartao_sd', nome='Cartão SD', cat='leitura', desc='Pede a lista de arquivos do cartão (M20).'),
    dict(id='display', nome='Tela (display) e bipe', cat='leitura', desc='Escreve uma mensagem na tela da impressora (M117) e faz um bipe. Você confirma se viu/ouviu.'),
    dict(id='ventoinha_peca', nome='Ventoinha da peça', cat='leitura', desc='Liga a ventoinha da peça por 3 s. Você confirma se ouviu/viu girar.'),
    dict(id='cr_touch', nome='Sensor CR Touch (agulha)', cat='leitura', desc='Sobe/desce a agulha 6 vezes e mede a resposta (o mesmo da aba Sensor). Não mexe nos eixos.'),
    dict(id='aquecer_bico', nome='Aquecimento do bico', cat='aquece', desc='Esquenta o bico a 120 °C e mede a velocidade de subida. Depois desliga.'),
    dict(id='aquecer_mesa', nome='Aquecimento da mesa', cat='aquece', desc='Esquenta a mesa a 45 °C e mede a subida. Depois desliga.'),
    dict(id='motores', nome='Motores X, Y e Z', cat='mexe', desc='Faz HOME e mexe cada eixo um pouco. TIRE a peça da mesa. Você confirma se os três moveram suavemente.'),
    dict(id='extrusor', nome='Extrusor (empurra filamento)', cat='extrusor', desc='Esquenta o bico a 200 °C e empurra 5 mm de filamento (precisa de filamento carregado). Você confirma.'),
]
IDS = [t['id'] for t in TESTES]
CAT = {t['id']: t['cat'] for t in TESTES}
ESTADOS = {'ok': '✔', 'falha': '✖', 'aviso': '!', 'observar': '?', 'pulado': '–'}


class Parar(Exception):
    pass


class Contexto:
    """Conversa com a impressora (L = Linha da serial) e acompanha temperaturas."""
    def __init__(self, L, parar=lambda: False, ao_ler=None):
        self.L = L; self._parar = parar; self.ao_ler = ao_ler or (lambda l: None); self.bico = None; self.mesa = None

    def parou(self):
        if self._parar(): raise Parar()

    def enviar(self, cmd, limite=30):
        """Manda um comando e junta as linhas ate o 'ok'. Devolve (lista de linhas, recebeu_ok)."""
        self.parou(); self.L.tx(cmd); linhas = []; fim = time.time() + limite
        while time.time() < fim:
            self.parou(); l = self.L.rx()
            if not l: continue
            self.ao_ler(l); self._temps(l); linhas.append(l)
            if l.startswith('ok'): return linhas, True
            if any(k in l for k in ('Error', 'halted', 'Killed', 'STOP')): return linhas, False
        return linhas, False

    def _temps(self, l):
        m = re.search(r'T:(-?[\d.]+)\s*/?([\d.]*)', l)
        if m:
            try: self.bico = float(m.group(1))
            except ValueError: pass
        m = re.search(r'B:(-?[\d.]+)\s*/?([\d.]*)', l)
        if m:
            try: self.mesa = float(m.group(1))
            except ValueError: pass

    def temps(self):
        self.enviar('M105', 10); return self.bico, self.mesa

    def esperar(self, s):
        fim = time.time() + s
        while time.time() < fim: self.parou(); time.sleep(0.1)


# ---------------- os testes ----------------
def t_comunicacao(c):
    ls, ok = c.enviar('M115', 10); txt = ' '.join(ls)
    m = re.search(r'FIRMWARE_NAME:([^:]+?)\s+\w+:', txt) or re.search(r'FIRMWARE_NAME:(.*?)(?:\s+SOURCE|\s+PROTOCOL|$)', txt)
    mc = re.search(r'MACHINE_TYPE:([^:]+?)\s+\w+:', txt)
    if not ok or 'FIRMWARE' not in txt: return 'falha', 'O firmware não respondeu ao M115. Cabo USB / porta / outro programa usando a porta?'
    return 'ok', 'Firmware: %s%s' % ((m.group(1).strip() if m else '?'), (' · máquina: ' + mc.group(1).strip()) if mc else '')


def t_termistores(c):
    bico, mesa = c.temps()
    if bico is None or mesa is None: return 'falha', 'Não consegui ler a temperatura (bico=%s, mesa=%s).' % (bico, mesa)
    if bico < 0 or bico > 330 or mesa < 0 or mesa > 130: return 'falha', 'Valor absurdo (bico %.1f °C, mesa %.1f °C): termistor solto, em curto ou com mau contato.' % (bico, mesa)
    if bico < 5 or mesa < 5: return 'aviso', 'Bico %.1f °C / mesa %.1f °C: muito frio para um dia normal. Termistor solto? (um valor perto de 0 ou negativo costuma ser fio solto)' % (bico, mesa)
    if abs(bico - mesa) > 25: return 'aviso', 'Bico %.1f °C e mesa %.1f °C diferem bastante. Se a impressora estava desligada há horas, deviam ser parecidos (ambiente).' % (bico, mesa)
    return 'ok', 'Bico %.1f °C · mesa %.1f °C (coerente com o ambiente/estado).' % (bico, mesa)


def t_fins_de_curso(c):
    ls, ok = c.enviar('M119', 10)
    est = {}
    for l in ls:
        m = re.match(r'\s*(\w+)\s*:\s*(\w+)', l)
        if m and m.group(1).lower() not in ('ok', 'echo', 'reporting'): est[m.group(1).lower()] = m.group(2).upper()
    if not ok or not est: return 'falha', 'O M119 não devolveu o estado dos fins de curso.'
    txt = ' · '.join('%s=%s' % (k, 'ACIONADO' if v == 'TRIGGERED' else 'livre') for k, v in est.items())
    aci = [k for k, v in est.items() if v == 'TRIGGERED' and k.startswith(('x', 'y'))]
    if aci: return 'aviso', 'Parados com o carro fora do canto, mas %s está ACIONADO: ou o carro está no canto, ou o fim de curso está travado/em curto. (%s)' % (', '.join(aci), txt)
    return 'ok', txt + '  (para testar de verdade: aperte um fim de curso com o dedo e rode de novo; ele deve mudar para ACIONADO)'


def t_sensor_filamento(c):
    ls, ok = c.enviar('M412', 10); txt = ' '.join(ls)
    m = re.search(r'runout:?\s*(ON|OFF)', txt, re.I)
    l2, _ = c.enviar('M119', 10); fil = next((l for l in l2 if 'filament' in l.lower()), '')
    det = 'Detecção de fim de filamento: %s.' % (m.group(1).upper() if m else 'não informada pelo firmware')
    if fil: det += ' Agora o sensor vê: %s. (tire o filamento e rode de novo: o valor deve mudar)' % fil.strip()
    if not m and not fil: return 'aviso', 'O firmware não informou nada sobre sensor de filamento (talvez a impressora não tenha ou o recurso esteja desligado). ' + txt[:80]
    return 'ok', det


def t_cartao_sd(c):
    ls, ok = c.enviar('M20', 15); txt = ' '.join(ls)
    if 'Begin file list' in txt: n = max(0, sum(1 for l in ls if re.search(r'\.\w{2,4}\b', l)) - 0); return 'ok', 'Cartão SD lido (%d item(ns) listado(s)).' % n
    if 'SD init fail' in txt or 'No SD card' in txt: return 'aviso', 'Sem cartão SD (ou cartão com defeito/mal encaixado).'
    return 'aviso', 'O firmware não entendeu o M20 (talvez a impressora não use cartão pelo firmware).'


def t_display(c):
    ls, ok = c.enviar('M117 Teste do programa', 10)
    if not ok: return 'falha', 'O firmware recusou o M117 (mensagem na tela).'
    c.enviar('M300 S1000 P400', 10); c.esperar(1)
    return 'observar', 'Enviei "Teste do programa" para a tela e fiz um bipe. Apareceu na tela? Você ouviu o bipe?'


def t_ventoinha_peca(c):
    c.enviar('M106 S255', 10); c.esperar(3); c.enviar('M106 S0', 10)
    return 'observar', 'Liguei a ventoinha da peça (100%) por 3 s e desliguei. Ela girou?'


def t_cr_touch(c, app=None):
    if app is None: return 'aviso', 'Teste do CR Touch só roda dentro do programa (aba Sensor tem o teste completo).'
    itens, veredito, ok = app.rodar_sensor(c.L)
    return ('ok' if ok else 'falha'), veredito


def _subir(c, teto, alvo_cmd, ler, meta, max_s, min_subida, janela, nome):
    """Liga o aquecedor e acompanha a temperatura. Devolve (estado, detalhe)."""
    c.enviar(alvo_cmd, 10); t0 = time.time(); v0 = ler(); ini = v0 if v0 is not None else 0.0; chegou = None; marca = (t0, ini)
    while time.time() - t0 < max_s:
        c.esperar(2); c.enviar('M105', 10); v = ler()
        if v is None: continue
        if v >= meta - 2: chegou = time.time() - t0; break
        if time.time() - t0 >= janela and v - ini < min_subida:
            return 'falha', '%s subiu só %.1f °C em %d s (esperado ≥ %.0f °C). Aquecedor sem energia, solto ou termistor lendo errado.' % (nome, v - ini, janela, min_subida)
        if v > teto: return 'falha', '%s passou de %.0f °C sem parar (%.1f °C): termistor ou controle com problema. Desliguei.' % (nome, teto, v)
    if chegou is None:
        v = ler() or 0.0; return 'falha', '%s não chegou a %.0f °C em %d s (parou em %.1f °C).' % (nome, meta, max_s, v)
    return 'ok', '%s subiu de %.1f para %.0f °C em %d s (≈ %.2f °C/s).' % (nome, ini, meta, chegou, (meta - ini) / max(chegou, 1))


def t_aquecer_bico(c):
    c.temps()
    return _subir(c, 200, 'M104 S120', lambda: c.bico, 120, 120, 12, 25, 'Bico')


def t_aquecer_mesa(c):
    c.temps()
    return _subir(c, 90, 'M140 S45', lambda: c.mesa, 45, 240, 3, 60, 'Mesa')


def t_motores(c):
    ls, ok = c.enviar('G28', 300)
    if not ok: return 'falha', 'O HOME (G28) não terminou: %s' % (' '.join(ls)[-120:] or 'sem resposta')
    ls, _ = c.enviar('M114', 10); pos = ' '.join(ls)
    c.enviar('G91', 10)
    try:
        c.enviar('G1 Z10 F600', 60)
        for eixo in ('X', 'Y'):
            c.enviar('G1 %s20 F3000' % eixo, 30); c.enviar('G1 %s-20 F3000' % eixo, 30)
        c.enviar('G1 Z-10 F600', 60)
    finally:
        c.enviar('G90', 10)
    return 'observar', 'Fiz HOME e movi Z (+10 e volta), X e Y (20 mm e volta). Posição depois do home: %s. Os três eixos se moveram suave, sem barulho de batida ou pulo?' % (pos[:80] or '?')


def t_extrusor(c):
    try:
        st, det = _subir(c, 260, 'M104 S200', lambda: c.bico, 200, 240, 10, 40, 'Bico')
        if st != 'ok': return st, det
        c.enviar('M83', 10); c.enviar('G1 E5 F120', 60); c.esperar(1); c.enviar('G1 E-5 F600', 60); c.enviar('M82', 10)
    finally:
        c.enviar('M104 S0', 10)
    return 'observar', 'Esquentei a 200 °C e empurrei 5 mm de filamento (e puxei de volta). O filamento andou? A engrenagem do extrusor girou sem estalar?'


FUNCOES = {'comunicacao': t_comunicacao, 'termistores': t_termistores, 'fins_de_curso': t_fins_de_curso, 'sensor_filamento': t_sensor_filamento, 'cartao_sd': t_cartao_sd, 'display': t_display,
           'ventoinha_peca': t_ventoinha_peca, 'cr_touch': t_cr_touch, 'aquecer_bico': t_aquecer_bico, 'aquecer_mesa': t_aquecer_mesa, 'motores': t_motores, 'extrusor': t_extrusor}


def selecionar(ids, permitir_aquecer=False, permitir_mover=False, permitir_extrusor=False):
    """Lista de ids a rodar e os pulados (por falta de permissao). ids = lista ou 'seguros' (so leitura) ou 'todos'."""
    if ids in (None, 'seguros'): ids = [t['id'] for t in TESTES if t['cat'] == 'leitura']
    elif ids == 'todos': ids = IDS[:]
    rodar, pular = [], []
    for i in ids:
        if i not in FUNCOES: raise ValueError('teste desconhecido: %s (existentes: %s)' % (i, ', '.join(IDS)))
        cat = CAT[i]
        if (cat == 'aquece' and not permitir_aquecer) or (cat == 'mexe' and not permitir_mover) or (cat == 'extrusor' and not (permitir_aquecer and permitir_extrusor)): pular.append(i)
        else: rodar.append(i)
    return rodar, pular


def rodar(c, ids, app=None, perguntar=None, progresso=None):
    """Roda os testes em ordem (leitura, depois aquece, mexe, extrusor). perguntar(texto) -> True/False/None para os 'observar'. Sempre desliga bico/mesa/ventoinha no fim.
    Devolve lista de dicts {id, nome, estado, detalhe}."""
    nomes = {t['id']: t['nome'] for t in TESTES}; ordem = sorted(ids, key=lambda i: IDS.index(i)); out = []
    try:
        for i in ordem:
            if progresso: progresso(i, 'rodando', '')
            try:
                est, det = (FUNCOES[i](c, app) if i == 'cr_touch' else FUNCOES[i](c))
                if est == 'observar' and perguntar:
                    r = perguntar(det)
                    if r is True: est, det = 'ok', det.split('?')[0] + '? Você confirmou: SIM.'
                    elif r is False: est, det = 'falha', det.split('?')[0] + '? Você respondeu: NÃO.'
            except Parar: out.append(dict(id=i, nome=nomes[i], estado='pulado', detalhe='Teste parado por você.')); break
            except Exception as e: est, det = 'falha', 'Erro durante o teste: %s' % e
            out.append(dict(id=i, nome=nomes[i], estado=est, detalhe=det))
            if progresso: progresso(i, est, det)
    finally:
        for cmd in ('M104 S0', 'M140 S0', 'M106 S0', 'G90', 'M82'):
            try: c.L.tx(cmd); time.sleep(0.15)
            except Exception: pass
    return out
