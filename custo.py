"""Custo do filamento: quanto o G-code gasta (metros, gramas, R$) e o rolo atual (gramas que sobram).
Filamento 1,75 mm. Densidades: ABS 1,04 g/cm3, PLA 1,24, PETG 1,27, TPU 1,21."""
import os, re, json, math

PASTA = os.path.dirname(os.path.abspath(__file__))
ROLO_JSON = os.path.join(PASTA, 'rolo.json')
DENSIDADE = {'ABS': 1.04, 'PLA': 1.24, 'PETG': 1.27, 'TPU': 1.21}
AREA_MM2 = math.pi * (1.75 / 2) ** 2       # secao do filamento
PADRAO_ROLO = dict(material='ABS', gramas_total=1000, gramas_restantes=1000, preco_kg=120.0, nome='Rolo ABS')


def material_do_preset(nome_preset):
    n = (nome_preset or '').upper()
    for m in ('PETG', 'TPU', 'PLA', 'ABS'):
        if m in n: return m
    return 'ABS'


def metros_do_gcode(caminho_ou_linhas):
    """Soma o filamento empurrado (E positivo) no G-code. Entende M82/M83 (E absoluto/relativo) e G92 E."""
    linhas = caminho_ou_linhas if isinstance(caminho_ou_linhas, list) else open(caminho_ou_linhas, encoding='utf-8', errors='ignore')
    e_abs = True; e = 0.0; total = 0.0
    rx = re.compile(r'E(-?[\d.]+)')
    for l in linhas:
        if l.startswith('M82'): e_abs = True; continue
        if l.startswith('M83'): e_abs = False; continue
        if l.startswith('G92'):
            m = rx.search(l)
            if m: e = float(m.group(1))
            continue
        if l.startswith(('G1', 'G0')):
            m = rx.search(l.split(';')[0])
            if not m: continue
            v = float(m.group(1))
            if e_abs:
                if v > e: total += v - e
                e = v
            else:
                if v > 0: total += v
    return total / 1000.0


def calcular(caminho_gcode, material='ABS', preco_kg=120.0):
    """Devolve dict(metros, gramas, reais, material). Usa ';Filament used:' do Cura se for > 0, senao soma os E."""
    m = 0.0
    try:
        with open(caminho_gcode, encoding='utf-8', errors='ignore') as f:
            for _ in range(40):
                l = f.readline()
                mm = re.match(r';Filament used:\s*([\d.]+)m', l)
                if mm: m = float(mm.group(1)); break
    except Exception: pass
    if m <= 0: m = metros_do_gcode(caminho_gcode)
    dens = DENSIDADE.get(material, 1.04)
    g = m * 1000 * AREA_MM2 * dens / 1000.0          # mm3 -> cm3 (/1000) -> g
    return dict(metros=round(m, 2), gramas=round(g, 1), reais=round(g * preco_kg / 1000.0, 2), material=material)


def texto(c):
    return '%.1f m · %.0f g · R$ %.2f de %s' % (c['metros'], c['gramas'], c['reais'], c['material'])


class Rolo:
    def __init__(self):
        self.d = dict(PADRAO_ROLO)
        try: self.d.update(json.load(open(ROLO_JSON, encoding='utf-8')))
        except Exception: pass

    def salvar(self):
        try: json.dump(self.d, open(ROLO_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception: pass

    def da(self, gramas):
        """O rolo da para essa impressao? Devolve (bool, texto)."""
        r = float(self.d.get('gramas_restantes', 0))
        if gramas <= 0: return True, ''
        if r <= 0: return True, 'Rolo sem cadastro de gramas (coloque quanto sobra na aba Filamento).'
        if gramas > r: return False, 'O ROLO NÃO DÁ: a impressão gasta %.0f g e sobram só %.0f g no %s.' % (gramas, r, self.d.get('nome', 'rolo'))
        if gramas > r * 0.85: return True, 'Atenção: a impressão gasta %.0f g e sobram %.0f g (vai ficar no fim do rolo).' % (gramas, r)
        return True, 'Rolo ok: sobram %.0f g, a impressão gasta %.0f g.' % (r, gramas)

    def descontar(self, gramas):
        self.d['gramas_restantes'] = max(0.0, float(self.d.get('gramas_restantes', 0)) - float(gramas)); self.salvar()
        return self.d['gramas_restantes']
