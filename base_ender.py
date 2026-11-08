"""Imprimir na Ender-3 V3 SE: escolhe o arquivo (STL ou G-code), mostra o tempo e manda para a impressora pelo cabo USB.
- STL: fatia aqui com o CuraEngine (receita ABS que deu certo ontem, ou PLA).
- G-code (do Cura, 'Salvar no Disco'): troca o inicio pelo inicio seguro (mesa primeiro, G28, nivelamento salvo, ventoinha desligada).
- Manda linha a linha esperando o 'ok'. Em erro, desliga bico e mesa. Botao PARAR a qualquer momento.
- A impressora (chip CH340) e achada sozinha em qualquer COM.
"""
import os, re, sys, time, threading, subprocess, ctypes, json, tempfile
import avancado
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import serial, serial.tools.list_ports

PASTA = os.path.dirname(os.path.abspath(__file__))
CURA = r'C:\Program Files\UltiMaker Cura 5.13.0'
RES = CURA + r'\share\cura\resources'
PRESETS = {
    'ABS COMPLETO - qualidade 0,2 mm (receita que deu certo, ventoinha desligada)': dict(bico=245, mesa=100, ventoinha=False, brim=15, v=(20, 30, 45, 50, 50, 30)),
    'ABS RAPIDO - camada 0,28 mm, ~30% menos tempo (ventoinha desligada, NAO testado)': dict(bico=245, mesa=100, ventoinha=False, brim=15, v=(20, 40, 60, 70, 70, 40), camada=0.28, infill=10),
    'PLA (NAO testado ainda)': dict(bico=205, mesa=60, ventoinha=True, brim=0, v=(25, 25, 40, 50, 60, 40)),
}


AJUSTES_JSON = os.path.join(PASTA, 'presets_ajustes.json')   # escolhas da calibracao (bico, retracao) por preset


def preset_com_ajustes(nome):
    """Preset de fabrica + o que a calibracao gravou (temperatura do bico, retracao)."""
    p = dict(PRESETS[nome])
    try:
        a = json.load(open(AJUSTES_JSON, encoding='utf-8')).get(nome, {})
        if 'bico' in a: p['bico'] = int(a['bico'])
        if 'retracao' in a: p['retracao'] = float(a['retracao'])
    except Exception: pass
    return p


def achar_porta():
    for q in serial.tools.list_ports.comports():
        if q.vid == 0x1A86:
            return q.device
    return None


def inicio_seguro(bico, mesa, ventoinha):
    s = ['G90', 'M82', 'M140 S%d' % mesa, 'M104 S150', 'M190 S%d' % mesa, 'M109 S%d' % bico, 'G28', 'M501', 'M420 S1',
         'M106 S255' if ventoinha else 'M106 S0', 'G92 E0', 'G1 Z2 F600', 'G1 X10 Y20 F3000', 'G1 Z0.3 F600', 'G1 X10 Y120 E7 F1000',
         'G1 E6.2 F1800', 'G1 Z2 F600', 'G92 E0']
    return s


FIM = ['G92 E0', 'G1 E-1 F2100', 'G91', 'G1 Z10 F600', 'G90', 'G1 X10 Y200 F4000', 'M104 S0', 'M140 S0', 'M107', 'M84 X Y E']


INFO = dict(i_linha=0, fim_n=len(FIM))     # preenchido por preparar(): onde fica a linha de limpeza e quantos comandos tem o fim


def preparar(linhas, bico, mesa, ventoinha, av=None):
    """Troca o inicio e o fim do Cura pelo inicio/fim seguros (ou pelos da aba Avancado, se ligada). Devolve (comandos, tempo total s, tempo decorrido por comando, camada por comando, n camadas, indice onde comeca a peca)."""
    total = 0; ncam = 0
    for l in linhas:
        m = re.match(r';TIME_ELAPSED:([\d.]+)', l)
        if m: total = float(m.group(1))
        m = re.match(r';LAYER_COUNT:(\d+)', l)
        if m: ncam = int(m.group(1))
    corpo_i = next((i for i, l in enumerate(linhas) if l.startswith(';LAYER:0')), 0)
    corpo_f = next((i for i, l in enumerate(linhas) if l.startswith(';End of Gcode') or l.startswith(';end')), len(linhas))
    if corpo_f <= corpo_i: corpo_f = len(linhas)
    ativo = bool(av and av.get('ativo'))
    cmds, tempos, cams = [], [], []
    atual = 0.0; cam = 0
    ini_cmds, i_linha = avancado.inicio(av, bico, mesa, ventoinha)
    for c in ini_cmds:
        cmds.append(c); tempos.append(0.0); cams.append(0)
    ini_peca = len(cmds)
    camadas_extra = avancado.por_camada(av['por_camada']) if ativo else {}
    vm = av['ventoinha']['modo'] if ativo else 'preset'
    for l in linhas[corpo_i:corpo_f]:
        l = l.strip()
        m = re.match(r';TIME_ELAPSED:([\d.]+)', l)
        if m: atual = float(m.group(1))
        m = re.match(r';LAYER:(\d+)', l)
        if m:
            cam = int(m.group(1)) + 1
            if ativo:
                extra = list(camadas_extra.get(cam, []))
                if vm == 'camada' and cam == av['ventoinha']['camada']: extra.insert(0, 'M106 S%d' % avancado.pwm(av['ventoinha']['pct']))
                for c in extra: cmds.append(c); tempos.append(atual); cams.append(cam)
        if not l or l.startswith(';'): continue
        bruto = l; l = l.split(';')[0].strip()
        if vm != 'preset' and l.startswith(('M106', 'M107')): continue          # a ventoinha e controlada pela aba Avancado
        if l.startswith('M104') and 'CALIB' in bruto.upper(): pass          # torre de calibracao: troca de temperatura por andar
        elif l.startswith(('M104', 'M109', 'M140', 'M190', 'G28', 'G29')): continue
        cmds.append(l); tempos.append(atual); cams.append(cam)
    fim_cmds = avancado.fim(av)
    for c in fim_cmds:
        cmds.append(c); tempos.append(total); cams.append(cam)
    INFO.update(i_linha=i_linha, fim_n=len(fim_cmds))
    return cmds, total, tempos, cams, ncam or cam, ini_peca


def centralizar_stl(stl):
    """Copia o STL com o centro (X,Y) em 0 e a base em Z=0, para o CuraEngine pôr a peça no MEIO da mesa (mesa 220x220)."""
    import trimesh
    m = trimesh.load(stl, force='mesh')
    b = m.bounds
    m.apply_translation([-(b[0][0] + b[1][0]) / 2, -(b[0][1] + b[1][1]) / 2, -b[0][2]])
    tam = b[1] - b[0]
    if tam[0] > 215 or tam[1] > 215 or tam[2] > 245:
        raise RuntimeError('A peca nao cabe na mesa: %.0f x %.0f x %.0f mm (limite 220 x 220 x 250)' % tuple(tam))
    saida = os.path.join(tempfile.gettempdir(), 'ender_centrado_' + os.path.basename(stl))
    m.export(saida)
    return saida


def fatiar(stl, saida, p):
    env = dict(os.environ, CURA_ENGINE_SEARCH_PATH=RES + r'\definitions;' + RES + r'\extruders;' + RES)
    t0, v = p['bico'], p['v']
    ades = p.get('adesao') or ('brim' if p['brim'] else 'skirt')
    extra = []
    if ades == 'raft': extra += ['-s', 'raft_margin=5', '-s', 'raft_layers=2']
    sup = p.get('suporte', 'nenhum')
    if sup in ('mesa', 'tudo'):
        extra += ['-s', 'support_enable=true', '-s', 'support_type=' + ('buildplate' if sup == 'mesa' else 'everywhere'), '-s', 'support_angle=%d' % p.get('sup_angulo', 50),
                  '-s', 'support_infill_rate=%d' % p.get('sup_dens', 15), '-s', 'support_pattern=%s' % p.get('sup_padrao', 'zigzag'),
                  '-s', 'support_z_distance=%s' % p.get('sup_z', 0.2), '-s', 'support_xy_distance=%s' % p.get('sup_xy', 0.8),
                  '-s', 'support_interface_enable=%s' % ('true' if p.get('sup_teto', True) else 'false'),
                  '-s', 'support_roof_enable=%s' % ('true' if p.get('sup_teto', True) else 'false')]      # o CuraEngine le o 'roof' direto (o pai nao propaga sozinho)
        if p.get('sup_estrutura') == 'arvore': extra += ['-s', 'support_structure=tree', '-s', 'min_wall_line_width=0.3']      # suporte em ARVORE (galhos): melhor para pecas curvas/organicas
        for k in ('support_extruder_nr', 'support_infill_extruder_nr', 'support_extruder_nr_layer_0', 'support_interface_extruder_nr', 'support_roof_extruder_nr', 'support_bottom_extruder_nr'):
            extra += ['-s', k + '=0']
        extra += ['-s', 'minimum_support_area=2', '-s', 'minimum_interface_area=10', '-s', 'support_horizontal_expansion=0.2', '-s', 'support_bottom_enable=false',
                  '-s', 'support_z_seam_away_from_model=true']      # sem este valor o CuraEngine fecha com erro quando ha suporte      # sem isto o CuraEngine fecha com erro (nao sabe qual extrusor faz o suporte)
    for k_, v_ in p.get('extra_cura', []): extra += ['-s', '%s=%s' % (k_, v_)]      # ajustes extras da aba Avancado (chave=valor)
    ventoinha = 'true' if p['ventoinha'] else 'false'
    glob = ['-s', 'machine_center_is_zero=false', '-s', 'machine_start_gcode=;start', '-s', 'machine_end_gcode=;end',
            '-s', 'roofing_layer_count=0', '-s', 'flooring_layer_count=0', '-s', 'material_diameter=1.75',
            '-s', 'material_print_temperature=%d' % t0, '-s', 'material_print_temperature_layer_0=%d' % t0,
            '-s', 'material_bed_temperature=%d' % p['mesa'], '-s', 'material_bed_temperature_layer_0=%d' % p['mesa'],
            '-s', 'cool_fan_enabled=' + ventoinha, '-s', 'adhesion_type=' + ades,
            '-s', 'brim_line_count=%d' % max(p['brim'], 1), '-s', 'layer_height=%s' % p.get('camada', 0.2), '-s', 'layer_height_0=0.2',
            '-s', 'wall_line_count=2', '-s', 'top_layers=4', '-s', 'bottom_layers=4', '-s', 'infill_sparse_density=%d' % p.get('infill', 15),
            '-s', 'speed_print_layer_0=%d' % v[0], '-s', 'speed_wall_0=%d' % v[1], '-s', 'speed_wall_x=%d' % v[2],
            '-s', 'speed_infill=%d' % v[3], '-s', 'speed_print=%d' % v[4], '-s', 'speed_topbottom=%d' % v[5], '-s', 'speed_travel=120',
            '-s', 'retraction_enable=true', '-s', 'retraction_amount=%s' % p.get('retracao', 0.8), '-s', 'retraction_speed=35', '-s', 'retraction_hop_enabled=false',
            '-s', 'acceleration_enabled=false', '-s', 'jerk_enabled=false', '-s', 'mesh_position_x=0', '-s', 'mesh_position_y=0']
    ext = ['-e0', '-s', 'extruder_nr=0', '-s', 'material_diameter=1.75', '-s', 'material_print_temperature=%d' % t0,
           '-s', 'material_bed_temperature=%d' % p['mesa'], '-s', 'cool_fan_enabled=' + ventoinha,
           '-s', 'adhesion_type=' + ades, '-s', 'retraction_amount=%s' % p.get('retracao', 0.8)]
    if not os.path.basename(stl).startswith('mesa_'):   # 'mesa_*.stl' vem da Mesa 3D, ja posicionado em relacao ao centro da mesa
        stl = centralizar_stl(stl)   # STL com origem fora do centro caia na borda da mesa: centraliza no meio e apoia na mesa (z=0)
    cmd = [CURA + r'\CuraEngine.exe', 'slice', '-j', RES + r'\definitions\creality_ender3v3se.def.json'] + glob + extra + ext + ['-l', stl, '-o', saida]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True, creationflags=0x08000000 | 0x00004000)
    return os.path.isfile(saida) and os.path.getsize(saida) > 1000


