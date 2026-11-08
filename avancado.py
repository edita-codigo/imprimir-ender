"""Modo AVANCADO: mexer no que a impressora faz do comeco ao fim (aba "Avançado").

Tudo vale so quando o botao "Usar os ajustes avançados" esta ligado (desligado = o comportamento de sempre).
  - Inicio: Home (sensor), carregar o mapa de nivelamento, linha de limpeza
  - Fim: cada passo pode ser desligado (subir o bico, estacionar, esfriar, ventoinha, soltar motores...)
  - Ventoinha: do filamento escolhido / sempre desligada / fixa / so a partir de uma camada
  - Velocidade e fluxo (%), G-code extra antes e depois, comandos em camadas especificas
  - Ajustes extras do fatiador (CuraEngine), um por linha: chave=valor
Os valores ficam em avancado.json. Para outra impressora, use o perfil_impressora.json (perfil.py)."""
import os, re, json

PASTA = os.path.dirname(os.path.abspath(__file__))
ARQ = os.path.join(PASTA, 'avancado.json')
PADRAO = dict(
    ativo=False,
    inicio=dict(home=True, mapa=True, linha=True),
    fim=dict(retrair=True, subir=True, estacionar=True, bico=True, mesa=True, ventoinha=True, motores=True),
    ventoinha=dict(modo='preset', pct=100, camada=3),
    velocidade=100, fluxo=100,
    gcode_antes='', gcode_depois='', por_camada='', fatiador_extra='',
)
MODOS_VENT = {'preset': 'Como o filamento escolhido (ABS = desligada)', 'desligada': 'Sempre desligada', 'fixa': 'Ligada o tempo todo', 'camada': 'Desligada até a camada…'}
FIM_PASSOS = [('retrair', 'Puxar um pouco o filamento (não escorrer)', ['G92 E0', 'G1 E-1 F2100']), ('subir', 'Subir o bico 10 mm', ['G91', 'G1 Z10 F600', 'G90']),
              ('estacionar', 'Estacionar o bico no canto', ['G1 X10 Y200 F4000']), ('bico', 'Desligar o bico', ['M104 S0']), ('mesa', 'Desligar a mesa', ['M140 S0']),
              ('ventoinha', 'Desligar a ventoinha', ['M107']), ('motores', 'Soltar os motores', ['M84 X Y E'])]
PERIGOSAS = re.compile(r'^(M112|M502|M500|M501|M92|M851|M301|M304|M302|M205|M201|M203|M206|M290|M999|M997|M0|M1|M600|M81|M80)\b', re.I)


def carregar():
    c = json.loads(json.dumps(PADRAO))
    try:
        d = json.load(open(ARQ, encoding='utf-8'))
        c['ativo'] = bool(d.get('ativo', False))
        for sec in ('inicio', 'fim'):
            for k in c[sec]:
                if k in (d.get(sec) or {}): c[sec][k] = bool(d[sec][k])
        v = d.get('ventoinha') or {}
        if v.get('modo') in MODOS_VENT: c['ventoinha']['modo'] = v['modo']
        for k, lo, hi in (('pct', 0, 100), ('camada', 1, 5000)):
            try: c['ventoinha'][k] = int(max(lo, min(hi, float(v.get(k, c['ventoinha'][k])))))
            except (TypeError, ValueError): pass
        for k in ('velocidade', 'fluxo'):
            try: c[k] = int(max(20, min(300, float(d.get(k, 100)))))
            except (TypeError, ValueError): pass
        for k in ('gcode_antes', 'gcode_depois', 'por_camada', 'fatiador_extra'): c[k] = str(d.get(k, ''))[:5000]
    except Exception: pass
    return c


def salvar(c):
    try: json.dump(c, open(ARQ, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def linhas_gcode(txt):
    """Comandos de um texto (uma por linha; comentarios com ; sao tirados)."""
    out = []
    for l in (txt or '').splitlines():
        l = l.split(';')[0].strip()
        if l: out.append(l)
    return out


def por_camada(txt):
    """'5: M106 S128' -> {5: ['M106 S128']} (varias linhas na mesma camada juntam)."""
    d = {}
    for l in (txt or '').splitlines():
        l = l.split(';')[0].strip(); m = re.match(r'^(\d+)\s*[:=]\s*(.+)$', l)
        if m: d.setdefault(int(m.group(1)), []).append(m.group(2).strip())
    return d


def extras_fatiador(txt):
    """Linhas chave=valor -> lista [('chave','valor')] (so nomes simples; o resto e ignorado)."""
    out = []
    for l in (txt or '').splitlines():
        l = l.split('#')[0].strip(); m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*([^\s].*)$', l)
        if m: out.append((m.group(1), m.group(2).strip()))
    return out


def pwm(pct): return int(round(max(0, min(100, pct)) * 255 / 100.0))


def inicio(av, bico, mesa, vent_preset):
    """Comandos de inicio. Com av=None (ou desligado) e EXATAMENTE o inicio de sempre. Devolve (comandos, indice_da_linha_de_limpeza)."""
    base = ['G90', 'M82', 'M140 S%d' % mesa, 'M104 S150', 'M190 S%d' % mesa, 'M109 S%d' % bico]
    if not av or not av['ativo']:
        s = base + ['G28', 'M501', 'M420 S1', 'M106 S255' if vent_preset else 'M106 S0', 'G92 E0', 'G1 Z2 F600', 'G1 X10 Y20 F3000', 'G1 Z0.3 F600', 'G1 X10 Y120 E7 F1000', 'G1 E6.2 F1800', 'G1 Z2 F600', 'G92 E0']
        return s, len(s) - 8
    s = list(base)
    if av['inicio']['home']:
        s.append('G28')
        if av['inicio']['mapa']: s += ['M501', 'M420 S1']
    m = av['ventoinha']['modo']
    s.append('M106 S%d' % (255 if (m == 'preset' and vent_preset) else pwm(av['ventoinha']['pct']) if m == 'fixa' else 0))
    if av['velocidade'] != 100: s.append('M220 S%d' % av['velocidade'])
    if av['fluxo'] != 100: s.append('M221 S%d' % av['fluxo'])
    s += linhas_gcode(av['gcode_antes'])
    ini_linha = len(s)
    if av['inicio']['linha']: s += ['G92 E0', 'G1 Z2 F600', 'G1 X10 Y20 F3000', 'G1 Z0.3 F600', 'G1 X10 Y120 E7 F1000', 'G1 E6.2 F1800', 'G1 Z2 F600', 'G92 E0']
    else: s += ['G92 E0', 'G1 Z2 F600']
    return s, ini_linha


def fim(av):
    """Comandos de fim (sem av = o de sempre)."""
    if not av or not av['ativo']: return [c for _, _, cs in FIM_PASSOS for c in cs]
    out = []
    for chave, _, cs in FIM_PASSOS:
        if av['fim'].get(chave, True): out += cs
    return out + linhas_gcode(av['gcode_depois'])


def gcode_seguro(cmd, permitir_outros=False):
    """Confere um comando da API de G-code livre. Devolve (ok, motivo)."""
    c = cmd.split(';')[0].strip()
    if not c: return False, 'comando vazio'
    if not re.match(r'^[GMTgmt]\d+', c): return False, 'comando invalido: %s' % cmd[:40]
    if PERIGOSAS.match(c): return False, '%s e perigoso (muda a firmware, trava ou reinicia): faca pelo painel da impressora' % c.split()[0].upper()
    m = re.match(r'^M(?:104|109)\s+S(\d+)', c, re.I)
    if m and int(m.group(1)) > 275: return False, 'bico acima de 275 C nao e permitido'
    m = re.match(r'^M(?:140|190)\s+S(\d+)', c, re.I)
    if m and int(m.group(1)) > 110: return False, 'mesa acima de 110 C nao e permitida'
    if not permitir_outros and not re.match(r'^(G0|G1|G28|G90|G91|G92|M82|M83|M84|M104|M105|M106|M107|M109|M114|M115|M119|M140|M190|M155|M220|M221|M280|M410|M400|M300)\b', c, re.I):
        return False, '%s nao esta na lista simples; passe permitir_outros=true se tiver certeza' % c.split()[0].upper()
    return True, ''
