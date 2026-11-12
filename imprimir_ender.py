"""Imprimir na Ender-3 V3 SE - v3: painel ao vivo, aba do Sensor (teste do CR Touch), API local e pagina para o celular (token), envio de arquivo pela rede."""
import os, re, time, threading, ctypes, json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import serial
from base_ender import achar_porta, fatiar, preparar, PRESETS, PASTA, preset_com_ajustes
from mesa3d import SUPORTES, ADESOES
import servidor_rede
import mesa3d
import vigia as vg
import fila as fl
import timelapse as tl
import manual as mn
import calibracao as cb
import cores as cr
import suporte as sp
import avancado as avm
import avancado_ui
import zoo_cad
import zoo_ui
import mcp_ui
import editar_ui
import modelar_ui
import testes_hw
import testes_ui
import i18n
i18n.instalar()
import base_ender
import avisos
import custo
import winsound
from PIL import Image, ImageTk
import io

BG, CARD, TXT, DIM, VERDE, LARANJA, AZUL, VERM, AMARELO = '#0D1117', '#151B24', '#EAF0F8', '#93A0B5', '#38D39F', '#FF8A3D', '#5AB0FF', '#FF6B6B', '#F7C948'
LINHA = '#263041'
ETAPAS = ['Conectar', 'Esquentar a mesa', 'Esquentar o bico', 'Home (zerar eixos)', 'Linha de limpeza', 'Imprimindo a peca', 'Finalizar']
PROTO = os.path.join(PASTA, 'protocolo_serial.log')   # tudo que foi enviado (>>) e recebido (<<) da impressora
ULTIMO = os.path.join(PASTA, 'ultimo_arquivo.json')            # ultimo arquivo carregado (volta sozinho ao abrir o programa)
HISTORICO = os.path.join(PASTA, 'historico_impressoes.json')    # cada impressao: arquivo, inicio, resultado
RECEBIDOS = os.path.join(PASTA, 'recebidos')
NIVEL_JSON = os.path.join(PASTA, 'nivelamento.json')              # ultimo nivelamento feito pelo botao 'Nivelar agora'
os.makedirs(RECEBIDOS, exist_ok=True)


def hms(s):
    s = int(max(s, 0))
    return '%dh %02dmin' % (s // 3600, (s % 3600) // 60) if s >= 3600 else '%dmin %02ds' % (s // 60, s % 60)


class Linha:
    """Porta serial com registro de tudo que vai e volta (para entender o que a impressora responde)."""
    def __init__(self, porta):
        self.s = serial.Serial(porta, 115200, timeout=1)
        self.f = open(PROTO, 'a', encoding='utf-8')
        self.f.write('\n===== %s porta %s =====\n' % (time.strftime('%d/%m %H:%M:%S'), porta))

    def tx(self, c):
        self.s.write((c + '\n').encode()); self.f.write(time.strftime('%H:%M:%S ') + '>> ' + c + '\n'); self.f.flush()

    def rx(self):
        l = self.s.readline().decode(errors='ignore').strip()
        if l and not l.startswith('T:'): self.f.write(time.strftime('%H:%M:%S ') + '<< ' + l + '\n'); self.f.flush()
        return l

    def fechar(self):
        try: self.s.close(); self.f.close()
        except Exception: pass


class Anel(tk.Canvas):
    """Anel de progresso (o 42% do desenho)."""
    def __init__(self, pai, tam=100):
        super().__init__(pai, width=tam, height=tam, bg=CARD, highlightthickness=0); self.tam = tam; self.set(0)

    def set(self, pc):
        self.delete('all'); t = self.tam; m = 10; pc = max(0, min(100, pc))
        self.create_oval(m, m, t - m, t - m, outline=LINHA, width=9)
        if pc > 0: self.create_arc(m, m, t - m, t - m, start=90, extent=-3.599 * pc, style='arc', outline=VERDE, width=9)
        self.create_text(t / 2, t / 2, text='%d%%' % pc, fill=TXT, font=('Segoe UI', 20, 'bold'))


class Medidor(tk.Canvas):
    def __init__(self, pai, titulo, cor):
        super().__init__(pai, bg=CARD, height=102, highlightthickness=1, highlightbackground=LINHA)
        self.titulo, self.cor = titulo, cor; self.set(0, 0)

    def set(self, atual, alvo):
        self.delete('all'); w = max(self.winfo_width(), 300)
        self.create_text(14, 14, text=self.titulo, anchor='w', fill=DIM, font=('Segoe UI', 10, 'bold'))
        self.create_text(14, 48, text='%.0f°C' % atual, anchor='w', fill=self.cor, font=('Segoe UI', 30, 'bold'))
        self.create_text(w - 14, 52, text=('alvo %.0f°C' % alvo) if alvo else 'desligado', anchor='e', fill=DIM, font=('Segoe UI', 11))
        pc = min(atual / alvo, 1.0) if alvo else 0
        self.create_rectangle(14, 80, w - 14, 90, fill=LINHA, outline='')
        self.create_rectangle(14, 80, 14 + (w - 28) * pc, 90, fill=VERDE if (alvo and abs(atual - alvo) < 3) else self.cor, outline='')
        self.create_text(w - 14, 14, text='%d%%' % int(pc * 100), anchor='e', fill=TXT, font=('Segoe UI', 10, 'bold'))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Imprimir na Ender-3 V3 SE'); self.configure(bg=BG)
        alt = max(640, min(960, self.winfo_screenheight() - 78))                 # em tela baixa (notebook, zoom do Windows) a janela nao passa por baixo da barra de tarefas
        self.geometry('1280x%d+%d+0' % (alt, max(0, (self.winfo_screenwidth() - 1280) // 2))); self.minsize(1180, min(820, alt))
        self.cmds = []; self.tempos = []; self.cams = []; self.total = 0; self.ncam = 0; self.ini_peca = 0; self.bico = 245; self.mesa = 100
        self.parar = False; self.imprimindo = False; self.ocupado = False; self.arquivo = ''; self.info_txt = ''; self.info_cor = DIM; self.aviso = None; self.porta_txt = ''
        self.v_sup = tk.StringVar(value=SUPORTES[0]); self.v_ang = tk.IntVar(value=50); self.v_ades = tk.StringVar(value=ADESOES[0])
        for v in (self.v_sup, self.v_ang, self.v_ades): v.trace_add('write', lambda *x: self.agendar_refatiar())
        c_ = sp.carregar(); self.SUPORTES_TXT = SUPORTES; self.av = avm.carregar(); self.i_linha = None
        self.v_sup_estr = tk.StringVar(value=c_['estrutura']); self.v_sup_pad_txt = tk.StringVar(value=sp.PADROES[c_['padrao']]); self.v_sup_dens = tk.IntVar(value=c_['dens'])
        self.v_sup_z = tk.DoubleVar(value=c_['z']); self.v_sup_xy = tk.DoubleVar(value=c_['xy']); self.v_sup_teto = tk.BooleanVar(value=c_['teto'])
        for v in (self.v_sup_estr, self.v_sup_pad_txt, self.v_sup_dens, self.v_sup_z, self.v_sup_xy, self.v_sup_teto): v.trace_add('write', lambda *x: (self.sup_salvar(), self.agendar_refatiar()))
        self.nivel = dict(rodando=False, msg='', feito=False, hora='', temp=0, pontos=0, erro='')
        try: self.nivel.update(json.load(open(NIVEL_JSON, encoding='utf-8')), rodando=False, msg='', erro='')
        except Exception: pass
        self.v_nivel_temp = tk.IntVar(value=60); self.v_auto_pular = tk.BooleanVar(value=True); self.nivel_espera = 180
        self.pasta = PASTA; self.logs = []; self.link = None; self.arquivo_pronto = False
        self.st = dict(etapa=-1, msg='Parado.', bico=0, bico_alvo=0, mesa=0, mesa_alvo=0, i=0, n=1, t_peca=None, falta=None, cam=0, hist=[], fim=None, erro=None, comeco=None)
        self.sensor = dict(rodando=False, itens=[], veredito='')
        self.parada_tipo = None; self.parada_motivo = ''; self.vg_msg = ''; self.vg_foto_teste = None; self._bip = None
        self.alarme = dict(ativo=False, visivel=False, novo=False, titulo='', msg='')
        self.vigia = vg.Vigia(self)
        # ---- v5: fila, time-lapse, pausa/troca de filamento, rolo e custo ----
        self.rolo = custo.Rolo(); self.custo_atual = None; self.altura_camada = 0.2; self.avisos_cfg = avisos.carregar()
        self.fila = fl.Fila(self); self.timelapse = tl.Timelapse(self); self.cores = cr.Cores(self); self.zoo = zoo_cad.Tarefa()
        self.v_pausa_on = tk.BooleanVar(value=False); self.v_pausa_cam = tk.IntVar(value=50); self.v_runout = tk.BooleanVar(value=True)
        self.pausado = False; self.pausa_pedida = False; self.pausa_cam = 0; self.pausa_cam_feita = False; self.fw_pausado = False
        self.continuar_evt = threading.Event(); self.purga_q = []; self._pos = dict(X=0.0, Y=0.0, Z=0.0, E=0.0, F=1500.0, rel=False, erel=False)
        # ---- topo ----
        topo = tk.Frame(self, bg=BG); topo.pack(fill='x', padx=18, pady=(12, 8))
        logo = tk.Canvas(topo, width=44, height=44, bg=BG, highlightthickness=0); logo.pack(side='left')
        logo.create_polygon(10, 2, 34, 2, 42, 10, 42, 34, 34, 42, 10, 42, 2, 34, 2, 10, fill=LARANJA, outline='')
        logo.create_polygon(22, 10, 34, 16, 34, 29, 22, 36, 10, 29, 10, 16, outline=BG, width=2, fill='')
        for p in ((22, 23, 34, 16), (22, 23, 10, 16), (22, 23, 22, 36)): logo.create_line(*p, fill=BG, width=2)
        tt = tk.Frame(topo, bg=BG); tt.pack(side='left', padx=(12, 0))
        tk.Label(tt, text='Ender-3 V3 SE', bg=BG, fg=TXT, font=('Segoe UI', 15, 'bold')).pack(anchor='w')
        tk.Label(tt, text='Central de impressão', bg=BG, fg=DIM, font=('Segoe UI', 9)).pack(anchor='w')
        linha_abas = tk.Frame(self, bg=BG); linha_abas.pack(fill='x', padx=18, pady=(0, 6))        # as abas ficam numa linha propria (sao 13; em tela pequena nao passam por cima do idioma/celular)
        pill = tk.Frame(linha_abas, bg=CARD, highlightthickness=1, highlightbackground=LINHA); pill.pack(side='left')
        self.tabs = {}
        for nome in ('Imprimir', 'Mesa 3D', 'Modelar', 'Criar peça', 'Fila', 'Cores', 'Testar impressora', 'Manual', 'Filamento', 'Vigia', 'Avançado', 'IA / MCP', 'Sensor'):
            b = tk.Button(pill, text=nome, command=lambda n=nome: self.aba(n), relief='flat', bd=0, font=('Segoe UI', 9, 'bold'), padx=7, pady=7, cursor='hand2')
            b.pack(side='left', padx=3, pady=3); self.tabs[nome] = b
        chip2 = tk.Frame(topo, bg=CARD, highlightthickness=1, highlightbackground=LINHA); chip2.pack(side='right', padx=(8, 0))
        self.lrede = tk.Label(chip2, text='Celular: ligando...', bg=CARD, fg=TXT, font=('Segoe UI', 8), anchor='w'); self.lrede.pack(side='left', padx=(8, 4), pady=6)
        tk.Button(chip2, text='Copiar', command=self.copiar_link, relief='flat', bg=LINHA, fg=TXT, bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', padx=6).pack(side='left', padx=(0, 5))
        chip1 = tk.Frame(topo, bg=CARD, highlightthickness=1, highlightbackground=LINHA); chip1.pack(side='right')
        chipi = tk.Frame(topo, bg=CARD, highlightthickness=1, highlightbackground=LINHA); chipi.pack(side='right', padx=(0, 8))
        self.v_idioma = tk.StringVar(value=i18n.IDIOMAS[i18n.atual()])
        om_i = tk.OptionMenu(chipi, self.v_idioma, *i18n.IDIOMAS.values(), command=self.trocar_idioma); om_i.config(bg=CARD, fg=TXT, activebackground=LINHA, activeforeground=TXT, highlightthickness=0, bd=0, font=('Segoe UI', 9, 'bold'), indicatoron=True); om_i.pack(padx=4, pady=3)
        self.lporta = tk.Label(chip1, text='', bg=CARD, fg=TXT, font=('Segoe UI', 8)); self.lporta.pack(padx=8, pady=6)
        self.fbanner = tk.Frame(self, bg=VERM)       # faixa vermelha do alarme (so aparece quando o vigia dispara)
        self.lban_t = tk.Label(self.fbanner, bg=VERM, fg='#0D1117', font=('Segoe UI', 16, 'bold')); self.lban_t.pack(side='left', padx=14, pady=10)
        self.lban_m = tk.Label(self.fbanner, bg=VERM, fg='#0D1117', font=('Segoe UI', 11, 'bold'), wraplength=760, justify='left', anchor='w'); self.lban_m.pack(side='left', fill='x', expand=True)
        tk.Button(self.fbanner, text='SILENCIAR E FECHAR', command=self.silenciar_alarme, bg='#0D1117', fg='white', relief='flat', bd=0, font=('Segoe UI', 11, 'bold'), padx=14, pady=8, cursor='hand2').pack(side='right', padx=14)
        self.corpo = tk.Frame(self, bg=BG); self.corpo.pack(fill='both', expand=True)
        self.f_imp = tk.Frame(self.corpo, bg=BG); self.f_sen = tk.Frame(self.corpo, bg=BG); self.f_mesa = tk.Frame(self.corpo, bg=BG); self.f_vigia = tk.Frame(self.corpo, bg=BG)
        self.f_fila = tk.Frame(self.corpo, bg=BG); self.f_man = tk.Frame(self.corpo, bg=BG); self.f_fil = tk.Frame(self.corpo, bg=BG); self.f_cor = tk.Frame(self.corpo, bg=BG); self.f_av = tk.Frame(self.corpo, bg=BG); self.f_zoo = tk.Frame(self.corpo, bg=BG); self.f_mcp = tk.Frame(self.corpo, bg=BG); self.f_edit = tk.Frame(self.corpo, bg=BG); self.f_test = tk.Frame(self.corpo, bg=BG); self.f_mod = tk.Frame(self.corpo, bg=BG)
        self.montar_imprimir(self.f_imp); self.montar_sensor(self.f_sen); self.montar_vigia(self.f_vigia); self.montar_fila(self.f_fila)
        self.painel_manual = mn.Manual(self.f_man, self); self.painel_manual.pack(fill='both', expand=True)
        self.painel_fil = cb.Filamento(self.f_fil, self); self.painel_fil.pack(fill='both', expand=True)
        self.painel_cores = cr.PainelCores(self.f_cor, self); self.painel_cores.pack(fill='both', expand=True)
        self.painel_av = avancado_ui.PainelAvancado(self.f_av, self); self.painel_av.pack(fill='both', expand=True)
        self.painel_zoo = zoo_ui.PainelZoo(self.f_zoo, self); self.painel_zoo.pack(fill='both', expand=True)
        self.painel_mcp = mcp_ui.PainelMCP(self.f_mcp, self); self.painel_mcp.pack(fill='both', expand=True)
        self.painel_edit = editar_ui.PainelEditar(self.f_edit, self); self.painel_edit.pack(fill='both', expand=True)
        self.painel_mod = modelar_ui.PainelModelar(self.f_mod, self); self.painel_mod.pack(fill='both', expand=True)      # criar + editar pecas (CAD), ligado ao MCP
        self.diag = dict(estado='parado', resultados=[], atual='', msg='', pulados=[])
        self.painel_testes = testes_ui.PainelTestes(self.f_test, self); self.painel_testes.pack(fill='both', expand=True)
        self.painel_mesa = mesa3d.Mesa(self.f_mesa, self); self.painel_mesa.pack(fill='both', expand=True)
        self.log = tk.Text(self, height=3, bg='#0A0D12', fg='#8FA3BC', font=('Consolas', 9), bd=0, highlightthickness=1, highlightbackground='#1B2330', state='disabled'); self.log.pack(fill='x', padx=18, pady=(4, 12))
        self.aba_atual = 'Imprimir'; self.aba('Imprimir')
        self.protocol('WM_DELETE_WINDOW', self.fechar)
        try:
            self.link = servidor_rede.iniciar(self)
        except Exception as e:
            self.link = None; self.say('Rede: ' + str(e))
        self.lrede.config(text=('Celular · ' + self.link.split('/?')[0].replace('http://', '')) if self.link else 'Celular: servidor de rede nao iniciou', fg='#C5CFDF' if self.link else VERM)
        try:
            u = json.load(open(ULTIMO, encoding='utf-8'))
            if os.path.isfile(u.get('arquivo', '')):
                if u.get('preset') in PRESETS: self.preset.set(u['preset'])
                threading.Thread(target=self.carregar, args=(u['arquivo'],), daemon=True).start(); self.say('Carregando o ultimo arquivo: ' + os.path.basename(u['arquivo']))
        except Exception: pass
        self.after(500, self.atualizar)

    def trocar_idioma(self, nome):
        cod = next((k for k, v in i18n.IDIOMAS.items() if v == nome), 'pt')
        if cod == i18n.atual(): return
        i18n.definir(cod)
        if messagebox.askyesno('Idioma / Language', 'Reiniciar o programa agora para trocar o idioma?\n(Se estiver imprimindo, escolha NÃO e reinicie depois.)', parent=self):
            if self.imprimindo or self.ocupado: messagebox.showinfo('Idioma / Language', 'A impressora está ocupada. Reinicie o programa quando terminar.', parent=self); return
            import subprocess, sys
            exe = sys.executable
            subprocess.Popen('cmd /c ping -n 4 127.0.0.1 >nul & start "" "%s" "%s"' % (exe, os.path.join(self.pasta, 'imprimir_ender.py')), shell=True, cwd=self.pasta, creationflags=0x08000000)
            self.after(300, lambda: os._exit(0))
        else:
            self.v_idioma.set(i18n.IDIOMAS[cod])

    def copiar_link(self):
        if self.link: self.clipboard_clear(); self.clipboard_append(self.link); self.say('Link copiado.')

    def aba(self, nome):
        for fr in (self.f_imp, self.f_sen, self.f_mesa, self.f_vigia, self.f_fila, self.f_man, self.f_fil, self.f_cor, self.f_av, self.f_zoo, self.f_mcp, self.f_edit, self.f_test, self.f_mod): fr.pack_forget()
        {'Imprimir': self.f_imp, 'Sensor': self.f_sen, 'Mesa 3D': self.f_mesa, 'Vigia': self.f_vigia, 'Fila': self.f_fila, 'Manual': self.f_man, 'Filamento': self.f_fil, 'Cores': self.f_cor, 'Avançado': self.f_av, 'Criar peça': self.f_zoo, 'IA / MCP': self.f_mcp, 'Editar peça': self.f_edit, 'Testar impressora': self.f_test, 'Modelar': self.f_mod}[nome].pack(fill='both', expand=True)
        self.aba_atual = nome
        if nome == 'Mesa 3D': self.painel_mesa.mostrar()
        if nome == 'IA / MCP': self.painel_mcp.atualizar()
        for n, b in self.tabs.items(): b.config(bg=LARANJA if n == nome else CARD, fg='#0D1117' if n == nome else '#C5CFDF', activebackground=LARANJA if n == nome else LINHA)

    def botao(self, pai, texto, cmd, cor, grande=False):
        return tk.Button(pai, text=texto, command=cmd, bg=cor, fg=TXT if cor in (LINHA, '#33405A') else '#0D1117', activebackground=cor, relief='flat', bd=0, cursor='hand2',
                         font=('Segoe UI', 14 if grande else 11, 'bold'), padx=14, pady=10 if grande else 6, disabledforeground='#5B677F')

    # ---------- telas ----------
    def card(self, pai, **kw):
        return tk.Frame(pai, bg=CARD, highlightthickness=1, highlightbackground=LINHA, **kw)

    def rotulo(self, pai, t, **kw):
        return tk.Label(pai, text=t, bg=CARD, fg=DIM, font=('Segoe UI', 9, 'bold'), anchor='w', **kw)

    def menu(self, pai, var, valores, largura=30):
        om = tk.OptionMenu(pai, var, *valores)
        om.config(bg=BG, fg=TXT, activebackground=LINHA, activeforeground=TXT, highlightthickness=1, highlightbackground=LINHA, bd=0, relief='flat', anchor='w', font=('Segoe UI', 10), width=largura)
        om['menu'].config(bg=CARD, fg=TXT, activebackground='#2f6fb5', activeforeground='white', font=('Segoe UI', 10))
        return om

    def montar_imprimir(self, f):
        linha1 = tk.Frame(f, bg=BG); linha1.pack(fill='x', padx=18, pady=(0, 8))
        linha1.columnconfigure(0, weight=5, uniform='c'); linha1.columnconfigure(1, weight=4, uniform='c')
        # ---- cartao do arquivo ----
        ca = self.card(linha1); ca.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        h = tk.Frame(ca, bg=CARD); h.pack(fill='x', padx=16, pady=(12, 4))
        self.rotulo(h, 'ARQUIVO').pack(side='left')
        self.bmesa = self.botao(h, 'Ver na Mesa 3D', lambda: self.aba('Mesa 3D'), LINHA); self.bmesa.config(fg=TXT); self.bmesa.pack(side='right', padx=(8, 0))
        self.bescolher = self.botao(h, 'Escolher arquivo', self.escolher, AZUL); self.bescolher.pack(side='right')
        self.larq = tk.Label(ca, text='nenhum arquivo', bg=CARD, fg=TXT, font=('Segoe UI', 14, 'bold'), anchor='w'); self.larq.pack(fill='x', padx=16)
        self.linfo = tk.Label(ca, text='', bg=CARD, fg=VERDE, font=('Segoe UI', 10, 'bold'), anchor='w', justify='left', wraplength=600); self.linfo.pack(fill='x', padx=16, pady=(2, 2))
        self.lcusto_imp = tk.Label(ca, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=600); self.lcusto_imp.pack(fill='x', padx=16, pady=(0, 6))
        g = tk.Frame(ca, bg=CARD); g.pack(fill='x', padx=16, pady=(0, 6)); g.columnconfigure(0, weight=1); g.columnconfigure(1, weight=1)
        self.preset = tk.StringVar(value=list(PRESETS)[0])
        self.rotulo(g, 'Filamento').grid(row=0, column=0, sticky='w', columnspan=2); self.menu(g, self.preset, list(PRESETS), 60).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(2, 6))
        self.rotulo(g, 'Suporte (base para partes no ar)').grid(row=2, column=0, sticky='w'); self.rotulo(g, 'Aderência à mesa').grid(row=2, column=1, sticky='w', padx=(8, 0))
        self.menu(g, self.v_sup, SUPORTES, 28).grid(row=3, column=0, sticky='ew', pady=(2, 0)); self.menu(g, self.v_ades, ADESOES, 28).grid(row=3, column=1, sticky='ew', padx=(8, 0), pady=(2, 0))
        self.botao(g, 'Ajustes do suporte... (estrutura, densidade, árvore)', lambda: sp.abrir(self), LINHA).grid(row=4, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        self.pular_sensor = tk.BooleanVar(value=False)
        tk.Checkbutton(ca, text='Pular o sensor (só se a impressora NÃO foi desligada)', variable=self.pular_sensor, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 9)).pack(fill='x', padx=14, pady=(2, 10))
        # ---- cartao do nivelamento + vigia ----
        cn = self.card(linha1); cn.grid(row=0, column=1, sticky='nsew', padx=(7, 0))
        self.rotulo(cn, 'NIVELAMENTO DA MESA').pack(fill='x', padx=16, pady=(12, 4))
        self.lnivel = tk.Label(cn, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=430); self.lnivel.pack(fill='x', padx=16)
        l4 = tk.Frame(cn, bg=CARD); l4.pack(fill='x', padx=16, pady=(10, 4))
        self.bnivel = self.botao(l4, 'Nivelar agora (mesa morna)', self.nivelar_agora, AMARELO); self.bnivel.pack(side='left')
        tk.Label(l4, text='mesa a', bg=CARD, fg=DIM).pack(side='left', padx=(12, 4))
        tk.Spinbox(l4, from_=30, to=100, increment=5, width=4, textvariable=self.v_nivel_temp, bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat', font=('Segoe UI', 11, 'bold')).pack(side='left')
        tk.Label(l4, text='°C', bg=CARD, fg=DIM).pack(side='left', padx=(3, 0))
        tk.Checkbutton(cn, text='Usar esse nivelamento sozinho nas próximas impressões', variable=self.v_auto_pular, bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14, pady=(2, 6))
        tk.Frame(cn, bg=LINHA, height=1).pack(fill='x', padx=16, pady=4)
        self.lvigia = tk.Label(cn, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=430); self.lvigia.pack(fill='x', padx=16, pady=(0, 10))
        # ---- linha 2: bico, mesa, progresso ----
        m = tk.Frame(f, bg=BG); m.pack(fill='x', padx=18, pady=(0, 8))
        m.columnconfigure(0, weight=1, uniform='m'); m.columnconfigure(1, weight=1, uniform='m'); m.columnconfigure(2, weight=2, uniform='m')
        self.mbico = Medidor(m, 'BICO', LARANJA); self.mbico.grid(row=0, column=0, sticky='nsew', padx=(0, 7))
        self.mmesa = Medidor(m, 'MESA', AZUL); self.mmesa.grid(row=0, column=1, sticky='nsew', padx=7)
        p = self.card(m); p.grid(row=0, column=2, sticky='nsew', padx=(7, 0))
        self.lpc = Anel(p, 100); self.lpc.pack(side='left', padx=14, pady=10)
        d = tk.Frame(p, bg=CARD); d.pack(side='left', fill='x', expand=True, padx=(0, 14))
        self.lmsg = tk.Label(d, text='Parado.', bg=CARD, fg=TXT, font=('Segoe UI', 12, 'bold'), anchor='w', wraplength=520, justify='left'); self.lmsg.pack(fill='x', pady=(10, 2))
        self.barra = tk.Canvas(d, bg=LINHA, height=10, highlightthickness=0); self.barra.pack(fill='x', pady=4)
        self.ltempo = tk.Label(d, text='', bg=CARD, fg='#C5CFDF', font=('Segoe UI', 10), anchor='w', wraplength=520, justify='left'); self.ltempo.pack(fill='x', pady=(2, 0))
        self.lcam = tk.Label(d, text='', bg=CARD, fg=TXT, font=('Segoe UI', 10, 'bold'), anchor='w'); self.lcam.pack(fill='x', pady=(0, 8))
        # ---- linha 3: etapas + grafico ----
        b = tk.Frame(f, bg=BG); b.pack(fill='both', expand=True, padx=18, pady=(0, 8))
        e = self.card(b, width=250); e.pack(side='left', fill='y', padx=(0, 7)); e.pack_propagate(False)
        self.rotulo(e, 'ETAPAS').pack(fill='x', padx=16, pady=(12, 4))
        self.letapas = []
        for t in ETAPAS:
            l = tk.Label(e, text='○  ' + t, bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', pady=0); l.pack(fill='x', padx=16, pady=0); self.letapas.append(l)
        gr = self.card(b); gr.pack(side='left', fill='both', expand=True, padx=(7, 0))
        self.rotulo(gr, 'TEMPERATURA · ÚLTIMOS MINUTOS').pack(fill='x', padx=16, pady=(12, 0))
        self.graf = tk.Canvas(gr, bg=CARD, highlightthickness=0, height=120); self.graf.pack(fill='both', expand=True, padx=10, pady=6)
        bt = tk.Frame(f, bg=BG); bt.pack(fill='x', padx=18, pady=(0, 4))
        bt.columnconfigure(0, weight=3, uniform='b'); bt.columnconfigure(1, weight=2, uniform='b'); bt.columnconfigure(2, weight=2, uniform='b')
        self.bimp = self.botao(bt, 'IMPRIMIR', self.imprimir, VERDE, grande=True); self.bimp.grid(row=0, column=0, sticky='ew', padx=(0, 6)); self.bimp.configure(state='disabled')
        self.bpausa = self.botao(bt, 'PAUSAR', self.pausar_agora, AMARELO, grande=True); self.bpausa.grid(row=0, column=1, sticky='ew', padx=6); self.bpausa.configure(state='disabled')
        self.bpar = tk.Button(bt, text='PARAR', command=self.parar_tudo, bg=BG, fg=VERM, activebackground='#3A1D22', activeforeground=VERM, relief='flat', bd=0, highlightthickness=2, highlightbackground=VERM,
                              disabledforeground='#6B3B41', cursor='hand2', font=('Segoe UI', 14, 'bold'), pady=9)
        self.bpar.grid(row=0, column=2, sticky='ew', padx=(6, 0)); self.bpar.configure(state='disabled')

    def montar_fila(self, f):
        corpo = tk.Frame(f, bg=BG); corpo.pack(fill='both', expand=True, padx=18)
        dir_ = tk.Frame(corpo, bg=BG, width=430); dir_.pack(side='right', fill='y', padx=(10, 0)); dir_.pack_propagate(False)
        esq = self.card(corpo); esq.pack(side='left', fill='both', expand=True)
        self.rotulo(esq, 'FILA DE IMPRESSÃO · as peças saem uma depois da outra').pack(fill='x', padx=16, pady=(12, 4))
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16)
        self.botao(r, '+ Adicionar arquivos…', self.fila_adicionar, AZUL).pack(side='left')
        self.botao(r, '+ O arquivo atual', self.fila_add_atual, LINHA).pack(side='left', padx=6)
        self.botao(r, 'Cópias…', self.fila_copias, LINHA).pack(side='left')
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(6, 0))
        self.botao(r, '▲', lambda: self.fila_mover(-1), LINHA).pack(side='left', padx=(0, 2)); self.botao(r, '▼', lambda: self.fila_mover(1), LINHA).pack(side='left')
        self.botao(r, 'Remover', self.fila_remover, LINHA).pack(side='left', padx=6); self.botao(r, 'Reativar', self.fila_reativar, LINHA).pack(side='left'); self.botao(r, 'Limpar prontas', lambda: (self.fila.limpar_prontas(), self.atualizar_fila(True)), LINHA).pack(side='left', padx=6)
        self.lfila = tk.Listbox(esq, bg=BG, fg=TXT, selectbackground='#2f6fb5', activestyle='none', bd=0, highlightthickness=1, highlightbackground=LINHA, font=('Consolas', 10), height=12, exportselection=False)
        self.lfila.pack(fill='both', expand=True, padx=16, pady=8)
        self.lfila_st = tk.Label(esq, text='', bg=CARD, fg=TXT, font=('Segoe UI', 12, 'bold'), anchor='w', justify='left', wraplength=700); self.lfila_st.pack(fill='x', padx=16)
        self.v_fila_auto = tk.BooleanVar(value=self.fila.auto)
        tk.Checkbutton(esq, text='Continuar sozinho, sem esperar eu tirar a peça (só se as peças soltam sozinhas da mesa)', variable=self.v_fila_auto, command=lambda: (setattr(self.fila, 'auto', bool(self.v_fila_auto.get())), self.fila.salvar()), bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14, pady=(4, 2))
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(4, 12))
        self.bfila_ini = self.botao(r, 'COMEÇAR A FILA', self.fila_comecar, VERDE, grande=True); self.bfila_ini.pack(side='left', fill='x', expand=True)
        self.bfila_cont = self.botao(r, 'TIREI A PEÇA, CONTINUAR', self.fila_continuar, LARANJA, grande=True); self.bfila_cont.pack(side='left', fill='x', expand=True, padx=8)
        self.botao(r, 'Pular próxima', lambda: (self.fila.pular(), self.atualizar_fila(True)), LINHA).pack(side='left')
        # ---- avisos ----
        ca = self.card(dir_); ca.pack(fill='x')
        self.rotulo(ca, 'AVISOS NO CELULAR (Pushover)').pack(fill='x', padx=16, pady=(12, 4))
        c = self.avisos_cfg; self.va = {k: tk.BooleanVar(value=bool(c.get(k, True))) for k in ('pushover', 'terminou', 'erro', 'vigia', 'tirar_peca', 'filamento', 'pausa')}
        def salvar_av(*x):
            for k, v in self.va.items(): self.avisos_cfg[k] = bool(v.get())
            avisos.salvar(self.avisos_cfg)
        for k, v in self.va.items(): v.trace_add('write', salvar_av)
        tk.Checkbutton(ca, text='Avisar no celular', variable=self.va['pushover'], bg=CARD, fg=VERDE, selectcolor=LINHA, activebackground=CARD, activeforeground=VERDE, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 11, 'bold')).pack(fill='x', padx=14)
        for k, t in (('terminou', 'quando a impressão terminar'), ('tirar_peca', 'quando precisar tirar a peça (fila)'), ('erro', 'quando der erro ou parar'), ('vigia', 'quando o vigia da câmera achar problema'), ('filamento', 'quando o filamento acabar'), ('pausa', 'quando pausar para trocar de cor')):
            tk.Checkbutton(ca, text=t, variable=self.va[k], bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=30)
        r = tk.Frame(ca, bg=CARD); r.pack(fill='x', padx=16, pady=(6, 4))
        self.botao(r, 'Testar aviso', lambda: self.avisar('Teste do programa Imprimir Ender: os avisos estão funcionando.', None), LINHA).pack(side='left')
        self.lav = tk.Label(ca, text='', bg=CARD, fg=DIM, font=('Segoe UI', 9), anchor='w', justify='left', wraplength=380); self.lav.pack(fill='x', padx=16, pady=(0, 10))
        # ---- time-lapse ----
        ct = self.card(dir_); ct.pack(fill='x', pady=(10, 0))
        self.rotulo(ct, 'TIME-LAPSE (vídeo da peça crescendo, pela câmera do vigia)').pack(fill='x', padx=16, pady=(12, 4))
        t = self.timelapse.cfg
        self.vt = dict(ativo=tk.BooleanVar(value=t['ativo']), modo=tk.StringVar(value=t['modo']), cada=tk.StringVar(value=str(t['cada'])), fps=tk.StringVar(value=str(t['fps'])), flash=tk.BooleanVar(value=t['flash']))
        def salvar_tl(*x):
            c = self.timelapse.cfg; c['ativo'] = bool(self.vt['ativo'].get()); c['modo'] = self.vt['modo'].get(); c['flash'] = bool(self.vt['flash'].get())
            try: c['cada'] = max(1, int(float(self.vt['cada'].get().replace(',', '.'))))
            except ValueError: pass
            try: c['fps'] = max(2, min(60, int(self.vt['fps'].get())))
            except ValueError: pass
            tl.salvar_cfg(c)
        for v in self.vt.values(): v.trace_add('write', salvar_tl)
        tk.Checkbutton(ct, text='Gravar time-lapse enquanto imprime', variable=self.vt['ativo'], bg=CARD, fg=VERDE, selectcolor=LINHA, activebackground=CARD, activeforeground=VERDE, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 11, 'bold')).pack(fill='x', padx=14)
        r = tk.Frame(ct, bg=CARD); r.pack(fill='x', padx=16, pady=2)
        tk.Label(r, text='Uma foto a cada', bg=CARD, fg=TXT).pack(side='left'); tk.Spinbox(r, from_=1, to=120, width=4, textvariable=self.vt['cada'], bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat').pack(side='left', padx=6)
        tk.Radiobutton(r, text='camadas', variable=self.vt['modo'], value='camadas', bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0).pack(side='left')
        tk.Radiobutton(r, text='minutos', variable=self.vt['modo'], value='minutos', bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0).pack(side='left', padx=4)
        r = tk.Frame(ct, bg=CARD); r.pack(fill='x', padx=16, pady=2)
        tk.Label(r, text='Vídeo a', bg=CARD, fg=TXT).pack(side='left'); tk.Spinbox(r, from_=2, to=60, width=4, textvariable=self.vt['fps'], bg=BG, fg=TXT, buttonbackground=LINHA, relief='flat').pack(side='left', padx=6); tk.Label(r, text='quadros por segundo', bg=CARD, fg=TXT).pack(side='left')
        tk.Checkbutton(ct, text='Ligar o flash do celular em cada foto', variable=self.vt['flash'], bg=CARD, fg=TXT, selectcolor=LINHA, activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14)
        self.ltl = tk.Label(ct, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=380); self.ltl.pack(fill='x', padx=16, pady=(4, 2))
        r = tk.Frame(ct, bg=CARD); r.pack(fill='x', padx=16, pady=(2, 12))
        self.botao(r, 'Abrir pasta dos vídeos', self.timelapse.abrir_pasta, LINHA).pack(side='left'); self.botao(r, 'Montar último vídeo', self.tl_montar_ultima, LINHA).pack(side='left', padx=6)
        tk.Label(ct, text='As fotos ficam em timelapse\\<data>_<peça>\\ e o vídeo é montado sozinho quando a impressão termina (mp4; se não der, GIF).', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=380, justify='left').pack(anchor='w', padx=16, pady=(0, 10))
        self._fila_chave = None

    # ---------- fila: botoes ----------
    def fila_adicionar(self):
        for a_ in filedialog.askopenfilenames(initialdir=PASTA, filetypes=[('Modelo ou G-code', '*.stl *.gcode *.gco'), ('Todos', '*.*')]):
            self.fila.adicionar(a_, self.preset.get())
        self.atualizar_fila(True)

    def fila_add_atual(self):
        o = getattr(self, 'arq_origem', '')
        if not o or not os.path.isfile(o): messagebox.showinfo('Fila', 'Escolha um arquivo na aba Imprimir primeiro.'); return
        self.fila.adicionar(o, self.preset.get()); self.atualizar_fila(True)

    def _fila_sel(self):
        s = self.lfila.curselection()
        if not s or s[0] >= len(self.fila.itens): return None
        return self.fila.itens[s[0]]

    def fila_copias(self):
        it = self._fila_sel()
        if not it: messagebox.showinfo('Fila', 'Selecione um item da fila.'); return
        from tkinter import simpledialog
        n = simpledialog.askinteger('Cópias', 'Quantas cópias a mais de %s?' % it['nome'], parent=self, initialvalue=1, minvalue=1, maxvalue=50)
        if n: self.fila.adicionar(it['caminho'], it.get('preset'), n); self.atualizar_fila(True)

    def fila_mover(self, d):
        it = self._fila_sel()
        if it: self.fila.mover(it['id'], d); self.atualizar_fila(True)

    def fila_remover(self):
        it = self._fila_sel()
        if it: self.fila.remover(it['id']); self.atualizar_fila(True)

    def fila_reativar(self):
        it = self._fila_sel()
        if it: self.fila.reativar(it['id']); self.atualizar_fila(True)

    def fila_comecar(self):
        if self.fila.estado in ('rodando', 'esperando_tirar'):
            self.fila.parar(); self.atualizar_fila(True); return
        if not messagebox.askyesno('Fila', '%d peça(s) na fila. Filamento carregado, mesa limpa e cabo USB ligado?\nComeçar a fila?' % len(self.fila.pendentes())): return
        r = self.fila.iniciar()
        if not r.get('ok'): messagebox.showerror('Fila', r.get('erro', 'erro'))
        self.atualizar_fila(True)

    def fila_continuar(self):
        r = self.fila.continuar()
        if not r.get('ok'): messagebox.showinfo('Fila', r.get('erro', 'erro'))
        self.atualizar_fila(True)

    def atualizar_fila(self, forcar=False):
        f = self.fila; ch = (len(f.itens), tuple((i['estado'], i.get('hora', '')) for i in f.itens), f.estado)
        if forcar or ch != self._fila_chave:
            self._fila_chave = ch; sel = self.lfila.curselection(); self.lfila.delete(0, 'end')
            for k, i in enumerate(f.itens):
                marca = {'aguardando': '○', 'imprimindo': '▶', 'concluida': '✔', 'erro': '✖', 'parada': '■', 'pulada': '–'}.get(i['estado'], '?')
                self.lfila.insert('end', ' %s  %2d. %-40s %-11s %s %s' % (marca, k + 1, i['nome'][:40], fl.ESTADOS.get(i['estado'], i['estado']), i.get('hora', ''), (i.get('resultado') or '')[:40] if i['estado'] in ('erro', 'parada') else ''))
                if i['estado'] == 'imprimindo': self.lfila.itemconfig('end', fg=AMARELO)
                elif i['estado'] == 'concluida': self.lfila.itemconfig('end', fg=VERDE)
                elif i['estado'] in ('erro', 'parada'): self.lfila.itemconfig('end', fg=VERM)
                elif i['estado'] == 'pulada': self.lfila.itemconfig('end', fg=DIM)
            if sel: self.lfila.selection_set(sel[0])
        n = len(f.pendentes())
        if f.estado == 'esperando_tirar': txt, cor = f.msg, LARANJA
        elif f.estado == 'rodando': txt, cor = (f.msg or 'Fila rodando') + '  ·  faltam %d' % n, VERDE
        else: txt, cor = (f.msg + '  ·  ' if f.msg else '') + ('%d peça(s) na fila.' % n if n else 'Fila vazia: adicione arquivos.'), TXT
        self.lfila_st.config(text=txt, fg=cor)
        self.bfila_ini.config(text='PARAR A FILA' if f.estado in ('rodando', 'esperando_tirar') else 'COMEÇAR A FILA', bg=VERM if f.estado in ('rodando', 'esperando_tirar') else VERDE, state='normal' if (f.estado != 'parada' or (n and not self.ocupado)) else 'disabled')
        self.bfila_cont.config(state='normal' if (f.estado == 'esperando_tirar' and not self.ocupado) else 'disabled', bg=LARANJA if f.estado == 'esperando_tirar' else '#4A3320')
        u = avisos.ultimo
        self.lav.config(text=('Último aviso %s: %s' % (u['hora'], 'enviado' if u['ok'] else 'FALHOU (%s)' % u['erro'])) if u['hora'] else 'Nenhum aviso enviado ainda.', fg=(VERDE if u['ok'] else VERM) if u['hora'] else DIM)
        s = self.timelapse.status()
        self.ltl.config(text=('Time-lapse %s' % ('LIGADO' if s['ativo'] else 'desligado')) + (' · %s · %d foto(s)' % (s['estado'], s['fotos']) if s['estado'] != 'desligado' else '') + ((' · ' + s['msg']) if s['msg'] else ''), fg=VERDE if s['ativo'] else DIM)

    def tl_montar_ultima(self):
        import glob
        pastas = sorted(glob.glob(os.path.join(tl.RAIZ, '*')))
        if not pastas: messagebox.showinfo('Time-lapse', 'Ainda não tem nenhuma pasta de time-lapse.'); return
        p = pastas[-1]; self.timelapse.msg = 'Montando o vídeo de %s...' % os.path.basename(p)
        def run():
            v = tl.montar_video(p, int(self.timelapse.cfg.get('fps', 12)), self.say); self.timelapse.msg = ('Vídeo pronto: %s' % os.path.basename(v)) if v else 'Não consegui montar (poucas fotos?)'
        threading.Thread(target=run, daemon=True).start()

    # ---------- avisos / custo ----------
    def avisar(self, texto, tipo, prioridade=0):
        try: avisos.enviar(texto, tipo=tipo, prioridade=prioridade, cfg=self.avisos_cfg, log=self.say)
        except Exception as e: self.say('Aviso falhou: %s' % e)

    def atualizar_custo(self):
        if self.arquivo and os.path.isfile(self.arquivo):
            try: self.custo_atual = custo.calcular(self.arquivo, self.rolo.d.get('material', custo.material_do_preset(self.preset.get())), float(self.rolo.d.get('preco_kg', 120)))
            except Exception: self.custo_atual = None

    def texto_custo(self):
        c = self.custo_atual
        if not c: return ''
        ok, aviso = self.rolo.da(c['gramas'])
        return 'Esta impressão gasta ' + custo.texto(c) + ((' · ' + aviso) if aviso else '')

    def texto_rolo(self):
        d = self.rolo.d; return '%s (%s): sobram %.0f g de %.0f g · R$ %.2f/kg' % (d.get('nome', 'Rolo'), d.get('material', ''), float(d.get('gramas_restantes', 0)), float(d.get('gramas_total', 0)), float(d.get('preco_kg', 0)))

    def cor_rolo(self):
        c = self.custo_atual
        if c and not self.rolo.da(c['gramas'])[0]: return VERM
        return TXT

    # ---------- pausa / troca de filamento ----------
    def pausar_agora(self):
        if not self.imprimindo or self.pausado: return {'ok': False, 'erro': 'nao esta imprimindo (ou ja esta pausado)'}
        self.pausa_pedida = True; self.st['msg'] = 'Pausando no fim do movimento atual...'; return {'ok': True}

    def continuar(self):
        if not self.pausado: return {'ok': False, 'erro': 'nao esta pausado'}
        self.continuar_evt.set(); return {'ok': True}

    def purgar(self, mm=40):
        if not self.pausado: return {'ok': False, 'erro': 'so na pausa'}
        self.purga_q.append(int(mm)); return {'ok': True}

    def _rastrear(self, c):
        """Guarda onde o bico esta (pelos comandos enviados) para voltar ao mesmo lugar depois de uma pausa."""
        p = self._pos
        if c.startswith('G90'): p['rel'] = False
        elif c.startswith('G91'): p['rel'] = True
        elif c.startswith('M82'): p['erel'] = False
        elif c.startswith('M83'): p['erel'] = True
        elif c.startswith('G92'):
            for k, v in re.findall(r'([XYZE])(-?[\d.]+)', c): p[k] = float(v)
        elif c.startswith(('G0', 'G1')):
            for k, v in re.findall(r'([XYZEF])(-?[\d.]+)', c.split(';')[0]):
                v = float(v)
                if k == 'F': p['F'] = v
                elif k == 'E': p['E'] = p['E'] + v if p['erel'] else v
                else: p[k] = p[k] + v if p['rel'] else v

    def _pausa(self, L, motivo, tipo='pausa'):
        """Estaciona o bico, espera CONTINUAR (tela ou celular), volta para a peca."""
        st = self.st; p = dict(self._pos); self.pausado = True; self.pausa_pedida = False; self.continuar_evt.clear(); self.purga_q = []
        st['msg'] = 'PAUSADO (%s). Bico estacionado no canto. Troque o filamento e toque em CONTINUAR.' % motivo
        for c in ('M83', 'G1 E-4 F1800', 'M82', 'G91', 'G1 Z10 F600', 'G90', 'G1 X10 Y200 F4000'):
            L.tx(c); self.aguardar(L, 60, True)
        self.say('Pausa: %s' % motivo); self.avisar('Impressão PAUSADA (%s). Troque o filamento e toque em CONTINUAR no celular ou no PC.' % motivo, tipo, prioridade=1)
        ult = time.time(); t0 = time.time()
        while not self.continuar_evt.is_set():
            if self.parar: raise SystemExit
            if self.purga_q:
                mm = self.purga_q.pop(0)
                if st['bico'] >= 175:
                    st['msg'] = 'Empurrando %d mm de filamento...' % mm
                    for c in ('M83', 'G1 E%d F200' % mm, 'M82'): L.tx(c); self.aguardar(L, 180, True)
                    st['msg'] = 'PAUSADO (%s). Toque em CONTINUAR quando o filamento novo estiver saindo limpo.' % motivo
                else: self.say('Purga ignorada: bico frio (%.0f)' % st['bico'])
            if time.time() - ult > 4: ult = time.time(); L.tx('M105'); self.aguardar(L, 5, True)
            time.sleep(0.2)
        self.continuar_evt.clear(); st['msg'] = 'Voltando para a peça...'
        if st['bico'] < self.bico - 5: L.tx('M109 S%d' % self.bico); self.aguardar(L, 900, True)
        for c in ('G90', 'G1 X%.3f Y%.3f F4000' % (p['X'], p['Y']), 'G1 Z%.3f F600' % p['Z'], 'M83', 'G1 E4 F1800', 'M82', 'G92 E%.5f' % p['E'], 'G1 F%d' % int(p.get('F') or 1500)):
            L.tx(c); self.aguardar(L, 60, True)
        if p['rel']: L.tx('G91'); self.aguardar(L, 10, True)
        self.pausado = False; st['msg'] = 'Imprimindo a peca'; self.say('Pausa terminada (%.0f s)' % (time.time() - t0))

    def _olhar_firmware(self, l, L):
        """Mensagens da impressora durante a impressao: fim de filamento / pausa da propria placa (M600)."""
        low = l.lower()
        if time.time() - getattr(self, '_fw_m108', 0) < 20: return      # acabou de continuar: a placa ainda pode repetir a mensagem
        if not self.fw_pausado and ('paused for user' in low or '//action:pause' in low or ('filament' in low and ('runout' in low or 'insert' in low))):
            self.fw_pausado = True; self.pausado = True; self.continuar_evt.clear()
            self.st['msg'] = 'A IMPRESSORA PAUSOU SOZINHA (fim de filamento?). Coloque filamento novo e toque em CONTINUAR.'
            self.say('Impressora pausou: ' + l[:100]); self.avisar('A impressora PAUSOU sozinha: parece que o FILAMENTO ACABOU. Coloque filamento novo e toque em CONTINUAR.', 'filamento', prioridade=1)
            try: self.vigia_aviso('Filamento acabou (ou a impressora pausou). Troque e toque em CONTINUAR.')
            except Exception: pass

    def montar_vigia(self, f):
        V = vg; cfg = self.vigia.cfg
        self.vv = dict(ativo=tk.BooleanVar(value=cfg['ativo']), cam=tk.StringVar(value=cfg['camera_url']), flash=tk.BooleanVar(value=cfg['flash']),
                       inter=tk.StringVar(value=str(cfg['intervalo_min'])), prov=tk.StringVar(value=cfg['provedor']), limiar=tk.IntVar(value=cfg['limiar']),
                       conf=tk.BooleanVar(value=cfg['confirmar']), acao=tk.StringVar(value=cfg['acao']), desl=tk.StringVar(value=str(cfg['desligar_apos_min'])),
                       alarme=tk.BooleanVar(value=cfg['alarme']), falhaia=tk.BooleanVar(value=cfg['avisar_falha_ia']),
                       chave={p: tk.StringVar(value='\n'.join(V.lista_chaves(cfg, p))) for p in V.PROVEDORES}, aleat=tk.BooleanVar(value=bool(cfg.get('aleatorio', False))), modelo={p: tk.StringVar(value=cfg['modelos'].get(p, V.MODELOS_PADRAO[p])) for p in V.PROVEDORES})
        v = self.vv
        for x in [v[k] for k in ('ativo', 'cam', 'flash', 'inter', 'prov', 'limiar', 'conf', 'acao', 'desl', 'alarme', 'falhaia', 'aleat')] + list(v['chave'].values()) + list(v['modelo'].values()):
            x.trace_add('write', lambda *a: self.vg_salvar())
        corpo = tk.Frame(f, bg=BG); corpo.pack(fill='both', expand=True, padx=18, pady=8)
        esq = tk.Frame(corpo, bg=CARD, width=600, highlightthickness=1, highlightbackground=LINHA); esq.pack(side='left', fill='y'); esq.pack_propagate(False)
        def titulo(t): tk.Label(esq, text=t, bg=CARD, fg=DIM, font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=16, pady=(8, 2))
        def chk(t, var): tk.Checkbutton(esq, text=t, variable=var, bg=CARD, fg=TXT, selectcolor='#263041', activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14)
        def entrada(pai, var, w=30, show=None): return tk.Entry(pai, textvariable=var, width=w, show=show, bg='#0D1117', fg=TXT, insertbackground=TXT, relief='flat', font=('Segoe UI', 10))
        tk.Checkbutton(esq, text='VIGIAR PELA CÂMERA enquanto imprime', variable=v['ativo'], bg=CARD, fg=VERDE, selectcolor='#263041', activebackground=CARD, activeforeground=VERDE, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 11, 'bold')).pack(fill='x', padx=14, pady=(12, 0))
        titulo('CÂMERA · celular com IP Webcam ou câmera IP')
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16)
        entrada(r, v['cam'], 34).pack(side='left', ipady=4); self.botao(r, 'Testar câmera', self.vg_testar_camera, AZUL).pack(side='left', padx=8)
        chk('Ligar o flash do celular para a foto (quarto escuro)', v['flash'])
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(2, 0))
        tk.Label(r, text='Flash agora:', bg=CARD, fg=TXT, font=('Segoe UI', 10)).pack(side='left')
        self.botao(r, 'Ligar', lambda: self.vg_flash(True), '#263041').pack(side='left', padx=6); self.botao(r, 'Desligar', lambda: self.vg_flash(False), '#263041').pack(side='left')
        tk.Label(r, text='(comandos do IP Webcam: /enabletorch e /disabletorch)', bg=CARD, fg=DIM, font=('Segoe UI', 8)).pack(side='left', padx=8)
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=(4, 0))
        tk.Label(r, text='Olhar a cada', bg=CARD, fg=TXT).pack(side='left'); tk.Spinbox(r, from_=1, to=60, width=4, textvariable=v['inter'], bg='#0D1117', fg=TXT, buttonbackground='#263041', relief='flat').pack(side='left', padx=6)
        tk.Label(r, text='minutos (a 1ª foto é 3 min depois de começar a peça)', bg=CARD, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        titulo('IA QUE ANALISA A FOTO · escolha qual usar (JEV, OpenAI ou Gemini: todas olham a imagem)')
        for p, nome in V.PROVEDORES.items():
            r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=14, pady=2)
            tk.Radiobutton(r, text=nome, variable=v['prov'], value=p, command=self.vg_trocar_prov, bg=CARD, fg=TXT, selectcolor='#263041', activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, width=15, anchor='w', font=('Segoe UI', 10, 'bold')).pack(side='left')
            tk.Label(r, text='modelo:', bg=CARD, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
            cb = ttk.Combobox(r, textvariable=v['modelo'][p], values=vg.MODELOS_SUGERIDOS.get(p, []), width=26, font=('Segoe UI', 10)); cb.pack(side='left', padx=6, ipady=2); self.cb_modelo = getattr(self, 'cb_modelo', {}); self.cb_modelo[p] = cb
            tk.Button(r, text='buscar da minha chave', command=lambda p=p: self.vg_buscar_modelos(p), bg='#263041', fg=TXT, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 9), padx=8).pack(side='left')
        self.lchaves_t = tk.Label(esq, text='', bg=CARD, fg=TXT, font=('Segoe UI', 9, 'bold'), anchor='w'); self.lchaves_t.pack(fill='x', padx=16, pady=(6, 0))
        rt = tk.Frame(esq, bg=CARD); rt.pack(fill='x', padx=16)
        self.txt_chaves = tk.Text(rt, height=4, width=52, bg='#0D1117', fg=TXT, insertbackground=TXT, relief='flat', font=('Consolas', 9), wrap='none'); self.txt_chaves.pack(side='left', fill='x', expand=True)
        sb = tk.Scrollbar(rt, command=self.txt_chaves.yview); sb.pack(side='left', fill='y'); self.txt_chaves.config(yscrollcommand=sb.set)
        self.txt_chaves.bind('<KeyRelease>', lambda e: self.vg_chaves_editou()); self.txt_chaves.bind('<<Paste>>', lambda e: self.after(50, self.vg_chaves_editou))
        rb = tk.Frame(esq, bg=CARD); rb.pack(fill='x', padx=16, pady=(2, 0))
        tk.Button(rb, text='juntar de arquivo…', command=self.vg_chave_arquivo, bg='#263041', fg=TXT, relief='flat', bd=0, cursor='hand2', font=('Segoe UI', 9), padx=8).pack(side='left')
        tk.Checkbutton(rb, text='usar em ordem aleatória', variable=v['aleat'], bg=CARD, fg=TXT, selectcolor='#263041', activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, font=('Segoe UI', 9)).pack(side='left', padx=10)
        tk.Label(esq, text='UMA CHAVE POR LINHA, sem limite (ex.: 10 chaves grátis da Gemini). Quando uma esgota (erro 429) ou é recusada, o vigia passa para a próxima. As chaves ficam só no arquivo _PRIVADO_vigia.json.', bg=CARD, fg=DIM, font=('Segoe UI', 8), wraplength=560, justify='left').pack(anchor='w', padx=16)
        self.vg_trocar_prov()
        titulo('QUANDO CONSIDERAR QUE DEU ERRADO')
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16)
        tk.Label(r, text='Chance de falha acima de', bg=CARD, fg=TXT).pack(side='left')
        tk.Scale(r, from_=30, to=95, orient='horizontal', variable=v['limiar'], bg=CARD, fg=TXT, troughcolor='#263041', highlightthickness=0, length=170, showvalue=True).pack(side='left', padx=6); tk.Label(r, text='%', bg=CARD, fg=TXT).pack(side='left')
        chk('Confirmar com uma 2ª foto 30 s depois (evita alarme falso)', v['conf'])
        titulo('O QUE FAZER QUANDO DER ERRADO')
        for chave, texto in V.ACOES.items():
            tk.Radiobutton(esq, text=texto, variable=v['acao'], value=chave, bg=CARD, fg=TXT, selectcolor='#263041', activebackground=CARD, activeforeground=TXT, bd=0, highlightthickness=0, anchor='w', font=('Segoe UI', 10)).pack(fill='x', padx=14)
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=36)
        tk.Label(r, text='mantendo: desligar sozinha depois de', bg=CARD, fg=DIM, font=('Segoe UI', 9)).pack(side='left'); tk.Spinbox(r, from_=0, to=240, width=4, textvariable=v['desl'], bg='#0D1117', fg=TXT, buttonbackground='#263041', relief='flat').pack(side='left', padx=6)
        tk.Label(r, text='min (0 = nunca)', bg=CARD, fg=DIM, font=('Segoe UI', 9)).pack(side='left')
        chk('Tocar ALARME no computador', v['alarme']); chk('Avisar se a IA ou a câmera falharem durante a impressão', v['falhaia'])
        r = tk.Frame(esq, bg=CARD); r.pack(fill='x', padx=16, pady=8)
        self.botao(r, 'TESTAR A IA AGORA (foto + análise)', self.vg_testar_ia, AMARELO).pack(side='left'); self.botao(r, 'Testar alarme', self.testar_alarme, '#263041').pack(side='left', padx=8)
        r = tk.Frame(corpo, bg=CARD, highlightthickness=1, highlightbackground=LINHA); r.pack(side='left', fill='both', expand=True, padx=(10, 0))
        tk.Label(r, text='ÚLTIMA FOTO ANALISADA', bg=CARD, fg=DIM, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=16, pady=(12, 4))
        self.lfoto = tk.Label(r, text='(ainda sem foto)', bg='#0D1117', fg=DIM, width=64, height=18); self.lfoto.pack(padx=16)
        self.lvg_res = tk.Label(r, text='', bg=CARD, fg=TXT, font=('Segoe UI', 13, 'bold'), anchor='w', justify='left', wraplength=520); self.lvg_res.pack(fill='x', padx=16, pady=(10, 2))
        self.lvg_est = tk.Label(r, text='', bg=CARD, fg=DIM, font=('Segoe UI', 10), anchor='w', justify='left', wraplength=520); self.lvg_est.pack(fill='x', padx=16)
        tk.Label(r, text='HISTÓRICO', bg=CARD, fg=DIM, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=16, pady=(10, 2))
        self.lhist = tk.Listbox(r, bg='#0D1117', fg=TXT, bd=0, highlightthickness=0, font=('Consolas', 9), height=6); self.lhist.pack(fill='both', expand=True, padx=16, pady=(0, 12))

    def vg_salvar(self):
        v = self.vv; c = self.vigia.cfg
        try:
            c.update(ativo=bool(v['ativo'].get()), camera_url=v['cam'].get().strip(), flash=bool(v['flash'].get()), provedor=v['prov'].get(), confirmar=bool(v['conf'].get()),
                     acao=v['acao'].get(), alarme=bool(v['alarme'].get()), avisar_falha_ia=bool(v['falhaia'].get()), limiar=int(v['limiar'].get()))
            try: c['intervalo_min'] = max(1.0, float(v['inter'].get().replace(',', '.')))
            except ValueError: pass
            try: c['desligar_apos_min'] = max(0, int(float(v['desl'].get().replace(',', '.'))))
            except ValueError: pass
            c['aleatorio'] = bool(v['aleat'].get())
            for p in vg.PROVEDORES: c['chaves'][p] = vg.lista_chaves({'chaves': {p: v['chave'][p].get()}}, p); c['modelos'][p] = v['modelo'][p].get().strip() or vg.MODELOS_PADRAO[p]
            vg.salvar_cfg(c)
        except Exception as e: self.say('Vigia: nao salvou a configuracao (%s)' % e)

    def vg_trocar_prov(self):
        """Mostra na caixa as chaves da IA escolhida."""
        p = self.vv['prov'].get(); self.txt_chaves.delete('1.0', 'end'); self.txt_chaves.insert('1.0', self.vv['chave'][p].get()); self.vg_chaves_contar()

    def vg_buscar_modelos(self, p):
        """Busca na conta (chave 1 do provedor) os modelos disponiveis e poe na lista do campo modelo."""
        linhas = self.txt_chaves.get('1.0', 'end').splitlines() if self.vv['prov'].get() == p else vg.lista_chaves(self.vigia.cfg, p)
        cfg = {'chaves': {p: [l.strip() for l in linhas if l.strip()]}}
        self.say('Vigia: buscando os modelos de %s...' % vg.PROVEDORES[p])
        def run():
            ms, msg = vg.listar_modelos(cfg, p)
            def fim():
                self.cb_modelo[p].config(values=ms); self.say('Vigia: ' + msg)
                messagebox.showinfo('Modelos', msg + ' Clique na seta ao lado de "modelo" para escolher.', parent=self)
            self.after(0, fim)
        threading.Thread(target=run, daemon=True).start()

    def vg_chaves_editou(self):
        p = self.vv['prov'].get(); self.vv['chave'][p].set(self.txt_chaves.get('1.0', 'end').strip()); self.vg_chaves_contar()

    def vg_chaves_contar(self):
        p = self.vv['prov'].get(); n = len(vg.lista_chaves({'chaves': {p: self.vv['chave'][p].get()}}, p))
        st = vg.status_chaves(self.vigia.cfg, p) if p == self.vigia.cfg.get('provedor') else dict(de_molho=0)
        self.lchaves_t.config(text='Chaves de %s: %d%s' % (vg.PROVEDORES[p], n, (' (%d de molho: cota esgotada ou recusada)' % st['de_molho']) if st.get('de_molho') else ''))

    def vg_chave_arquivo(self):
        a = filedialog.askopenfilename(title='Arquivo de texto com chaves (uma por linha)', filetypes=[('Texto', '*.txt'), ('Todos', '*.*')])
        if a:
            try:
                p = self.vv['prov'].get(); novas = open(a, encoding='utf-8', errors='ignore').read()
                self.vv['chave'][p].set(self.vv['chave'][p].get().strip() + '\n' + novas); self.vg_trocar_prov(); self.vg_salvar()
            except Exception as e: messagebox.showerror('Chave', 'Nao consegui ler: %s' % e)

    def vg_flash(self, ligar):
        self.vg_salvar()
        def run():
            try: self.vg_msg = vg.flash(self.vigia.cfg, ligar)
            except Exception as e: self.vg_msg = 'Flash: %s' % e
        threading.Thread(target=run, daemon=True).start()

    def no_tk(self, fn, timeout=90):
        """Roda fn na thread da tela (tkinter nao e thread-safe) e devolve o resultado. Usado pela API de rede."""
        box = {}; ev = threading.Event()
        def run():
            try: box['r'] = fn()
            except Exception as e: box['e'] = e
            ev.set()
        self.after(0, run)
        if not ev.wait(timeout): raise RuntimeError('a tela nao respondeu a tempo')
        if 'e' in box: raise box['e']
        return box['r']

    def api_cores(self):
        res, erro = self.cores.resolvidas()
        return {'ok': True, 'cfg': self.cores.cfg, 'camadas': [dict(camada=t['camada'], z=round(t['z'], 2), nome=t['nome']) for t in res], 'erro': erro, 'status': self.cores.status()}

    # ---------- API do vigia (usada pelo servidor_rede / MCP) ----------
    def api_vigia_flash(self, ligar):
        try: return {'ok': True, 'msg': vg.flash(self.vigia.cfg, bool(ligar))}
        except Exception as e: return {'ok': False, 'erro': str(e)}

    def api_vigia_foto(self):
        """Foto da camera agora (sem IA). Devolve JPEG em base64."""
        try:
            import base64
            return {'ok': True, 'jpg_base64': base64.b64encode(vg.preparar_imagem(vg.capturar(self.vigia.cfg))).decode()}
        except Exception as e: return {'ok': False, 'erro': str(e)}

    def api_vigia_testar(self):
        """Foto + analise da IA agora (gasta 1 uso da chave)."""
        try:
            r = self.vigia.checar()
            return {'ok': True, 'prob_falha': round(r['prob']), 'tipo': r['tipo'], 'motivo': r['motivo'], 'imagem_clara': r['ok'], 'provedor': r.get('provedor'), 'chave': '%s de %s' % (r.get('chave_n'), r.get('chave_total'))}
        except Exception as e: return {'ok': False, 'erro': str(e)}

    def api_vigia_ativar(self, ativo):
        try:
            self.vigia.cfg['ativo'] = bool(ativo); vg.salvar_cfg(self.vigia.cfg)
            self.after(0, lambda: self.vv['ativo'].set(bool(ativo)))
            return {'ok': True, 'ativo': bool(ativo), 'msg': 'Vigia %s. Ele só olha enquanto uma impressão está em andamento.' % ('ligado' if ativo else 'desligado')}
        except Exception as e: return {'ok': False, 'erro': str(e)}

    def vg_testar_camera(self):
        self.vg_salvar(); self.vg_msg = 'Tirando a foto...'
        def run():
            try: self.vg_foto_teste = vg.preparar_imagem(vg.capturar(self.vigia.cfg)); self.vg_msg = 'Câmera OK.'
            except Exception as e: self.vg_msg = 'Câmera com problema: %s' % e
        threading.Thread(target=run, daemon=True).start()

    def vg_testar_ia(self):
        self.vg_salvar(); self.vg_msg = 'Tirando a foto e analisando...'
        def run():
            try:
                r = self.vigia.checar(); self.vg_msg = 'Teste OK: chance de falha %.0f%% (%s).' % (r['prob'], vg.TIPOS.get(r['tipo'], r['tipo']))
            except Exception as e: self.vg_msg = 'Teste falhou: %s' % e
        threading.Thread(target=run, daemon=True).start()

    def _mostrar_jpg(self, jpg):
        im = Image.open(io.BytesIO(jpg)).convert('RGB'); w, h = im.size; esc = min(520.0 / w, 300.0 / h)
        self._img_vg = ImageTk.PhotoImage(im.resize((max(1, int(w * esc)), max(1, int(h * esc))))); self.lfoto.config(image=self._img_vg, text='', width=0, height=0)

    def atualizar_vigia(self):
        a = self.alarme; v = self.vigia; cfg = v.cfg
        if a['visivel']:
            if not self.fbanner.winfo_ismapped(): self.fbanner.pack(fill='x', padx=18, pady=(0, 6), before=self.corpo)
            self.lban_t.config(text=a['titulo']); self.lban_m.config(text=a['msg'])
            if a['novo']:
                a['novo'] = False; self.deiconify(); self.lift(); self.attributes('-topmost', True); self.after(4000, lambda: self.attributes('-topmost', False))
        elif self.fbanner.winfo_ismapped(): self.fbanner.pack_forget()
        if v.foto_nova and v.ultimo: v.foto_nova = False; self._mostrar_jpg(v.ultimo['jpg'])
        if self.vg_foto_teste: j, self.vg_foto_teste = self.vg_foto_teste, None; self._mostrar_jpg(j)
        u = v.ultimo
        if u:
            cor = VERM if (u['ok'] and u['prob'] >= cfg['limiar']) else (AMARELO if not u['ok'] else VERDE)
            self.lvg_res.config(text='%s · chance de falha %.0f%% · %s' % (u['hora'], u['prob'], vg.TIPOS.get(u['tipo'], u['tipo'])), fg=cor)
        est = 'Vigia %s' % ('LIGADO' if cfg['ativo'] else 'desligado'); prox = ''
        if v.proxima and self.imprimindo: prox = ' · próxima foto em %d s' % max(0, int(v.proxima - time.time()))
        self.lvg_est.config(text=est + (' · ' + v.estado if cfg['ativo'] and self.imprimindo else '') + prox + ((' · ' + self.vg_msg) if self.vg_msg else ''))
        if len(v.historico) != getattr(self, '_nh', -1):
            self._nh = len(v.historico); self.lhist.delete(0, 'end')
            for h in reversed(v.historico[-30:]): self.lhist.insert('end', '%s  %3.0f%%  %s' % (h['hora'], h['prob'], vg.TIPOS.get(h['tipo'], h['tipo'])))
        try:
            self.lvigia.config(text=('Vigia por câmera: ' + ('LIGADO (%s, a cada %s min)' % (vg.PROVEDORES[cfg['provedor']], cfg['intervalo_min']) if cfg['ativo'] else 'desligado') + ((' · última foto %s: %.0f%% de chance de falha' % (u['hora'], u['prob'])) if u else '')), fg=VERDE if cfg['ativo'] else DIM)
        except Exception: pass

    def montar_sensor(self, f):
        c = tk.Frame(f, bg=CARD); c.pack(fill='x', padx=18, pady=8)
        tk.Label(c, text='Teste do sensor de nivelamento (CR Touch)', bg=CARD, fg=TXT, font=('Segoe UI', 14, 'bold')).pack(anchor='w', padx=14, pady=(12, 2))
        tk.Label(c, wraplength=900, justify='left', bg=CARD, fg=DIM, font=('Segoe UI', 10), text=(
            'Como funciona: o sensor manda para a placa um sinal que muda conforme a posicao da agulha.\n'
            'O teste sobe e desce a agulha varias vezes (SO a agulha, nenhum eixo se move) e confere o sinal: agulha DESCIDA = "livre"; agulha RECOLHIDA = "acionado" (e assim mesmo neste firmware). '
            'Se o sinal nao acompanhar a agulha, a impressora para com o erro "BLTouch error" no Home. Nao esquenta nada e leva uns 40 s.')).pack(anchor='w', padx=14)
        self.bsens = self.botao(c, 'TESTAR O SENSOR AGORA', self.testar_sensor, AMARELO, grande=True); self.bsens.pack(fill='x', padx=14, pady=12)
        self.lsv = tk.Label(c, text='', bg=CARD, fg=TXT, font=('Segoe UI', 13, 'bold'), wraplength=900, justify='left', anchor='w'); self.lsv.pack(fill='x', padx=14, pady=(0, 12))
        r = tk.Frame(f, bg=CARD); r.pack(fill='both', expand=True, padx=18, pady=6)
        tk.Label(r, text='PASSOS DO TESTE', bg=CARD, fg=DIM, font=('Segoe UI', 10, 'bold')).pack(anchor='w', padx=14, pady=(10, 4))
        self.sitens = tk.Frame(r, bg=CARD); self.sitens.pack(fill='both', expand=True, padx=14, pady=(0, 10))

    def say(self, t):
        linha = time.strftime('%H:%M:%S ') + t
        self.logs.append(linha); self.logs = self.logs[-200:]
        self.pend_log = getattr(self, 'pend_log', []) + [linha]

    # ---------- arquivo ----------
    def escolher(self):
        a = filedialog.askopenfilename(initialdir=PASTA, filetypes=[('Modelo ou G-code', '*.stl *.gcode *.gco'), ('Todos', '*.*')])
        if a: threading.Thread(target=self.carregar, args=(a,), daemon=True).start()

    def carregar(self, a):
        """Prepara um arquivo; so um por vez (se mudar algo no meio, refatia depois)."""
        self._fatiando = True
        try: return self._carregar(a)
        finally:
            self._fatiando = False
            if getattr(self, '_ref_pend', False): self._ref_pend = False; self.after(0, self.agendar_refatiar)

    def _carregar(self, a):
        """Prepara um arquivo (STL ou G-code). Devolve dict para a API."""
        orig = a; self.arq_origem = a; self.larq_txt = a; self.arquivo_pronto = False; self.info_txt, self.info_cor = 'Preparando...', AMARELO
        p = preset_com_ajustes(self.preset.get()); p.update(self.opcoes_fatiar())
        try:
            if a.lower().endswith('.stl'):
                self.info_txt = 'Fatiando... (alguns segundos)'
                g = os.path.join(PASTA, os.path.splitext(os.path.basename(a))[0] + '_' + ('abs' if p['bico'] > 220 else 'pla') + '.gcode')
                if not fatiar(a, g, p):
                    self.info_txt, self.info_cor = 'Nao consegui fatiar este STL.', VERM; return {'ok': False, 'erro': self.info_txt}
                a = g
            linhas = open(a, encoding='utf-8', errors='ignore').read().splitlines()
            bico, mesa = p['bico'], p['mesa']
            for l in linhas[:400]:
                m = re.match(r'M(?:109|104) S(\d+)', l)
                if m and int(m.group(1)) > 180: bico = int(m.group(1)); break
            for l in linhas[:400]:
                m = re.match(r'M(?:190|140) S(\d+)', l)
                if m and int(m.group(1)) > 0: mesa = int(m.group(1)); break
            vent = False if bico > 220 else p['ventoinha']
            cmds, total, tempos, cams, ncam, ini = preparar(linhas, bico, mesa, vent, self.av)
            self.i_linha = base_ender.INFO['i_linha']
            if not total: total = len(cmds) * 0.25
            self.cmds, self.total, self.tempos, self.cams, self.ncam, self.ini_peca, self.bico, self.mesa, self.arquivo = cmds, total, tempos, cams, ncam, ini, bico, mesa, a
            self.info_txt = 'Pronto: %s de impressao  |  bico %d°C  |  mesa %d°C  |  %d camadas  |  ~6 min a mais para esquentar' % (hms(total), bico, mesa, ncam)
            self.altura_camada = 0.2
            for l in linhas[:60]:
                m = re.match(r';Layer height:\s*([\d.]+)', l)
                if m: self.altura_camada = float(m.group(1)); break
            self.atualizar_custo()
            try: self.cores.arquivo_novo(); self.after(0, self.painel_cores._preview)
            except Exception: pass
            self.info_cor = VERDE; self.arquivo_pronto = True; self.say('Arquivo pronto: ' + os.path.basename(a))
            try: json.dump({'arquivo': orig, 'preset': self.preset.get()}, open(ULTIMO, 'w', encoding='utf-8'))
            except Exception: pass
            return {'ok': True, 'arquivo': os.path.basename(a), 'info': self.info_txt, 'tempo_s': total}
        except Exception as e:
            self.info_txt, self.info_cor = 'Erro ao preparar: %s' % e, VERM; return {'ok': False, 'erro': str(e)}

    def preset_atual(self):
        return preset_com_ajustes(self.preset.get())

    def sup_cfg(self):
        """Ajustes de suporte lidos da tela (com limites seguros)."""
        inv = {v: k for k, v in sp.PADROES.items()}
        def num(v, lo, hi, padrao):
            try: return max(lo, min(hi, float(v.get())))
            except Exception: return padrao
        return dict(estrutura=self.v_sup_estr.get() if self.v_sup_estr.get() in sp.ESTRUTURAS else 'normal', padrao=inv.get(self.v_sup_pad_txt.get(), 'zigzag'),
                    dens=int(num(self.v_sup_dens, 3, 80, 15)), z=round(num(self.v_sup_z, 0.05, 1.0, 0.2), 2), xy=round(num(self.v_sup_xy, 0.2, 3.0, 0.8), 2), teto=bool(self.v_sup_teto.get()))

    def sup_salvar(self):
        sp.salvar(self.sup_cfg())

    def sup_aplicar(self, v):
        self.v_sup_estr.set(v['estrutura']); self.v_sup_pad_txt.set(sp.PADROES[v['padrao']]); self.v_sup_dens.set(v['dens'])
        self.v_sup_z.set(v['z']); self.v_sup_xy.set(v['xy']); self.v_sup_teto.set(v['teto'])
        if self.v_sup.get() == SUPORTES[0]: self.v_sup.set(SUPORTES[1])           # escolheu um modelo de suporte: liga o suporte

    def api_zoo(self, d=None):
        """GET: estado da criacao de pecas por texto (Zoo). POST {descricao, adicionar_na_mesa}: comeca (so se voce autorizou a API na aba Criar peca)."""
        cfg = zoo_cad.carregar_cfg()
        if d is not None:
            if not cfg['permitir_mcp']: return {'ok': False, 'erro': 'A API/IA nao esta autorizada a criar pecas com as suas chaves da Zoo. Marque a opcao na aba "Criar peca" se quiser.'}
            if self.zoo.estado == 'rodando': return {'ok': False, 'erro': 'ja esta criando uma peca'}
            if not zoo_cad.carregar_chaves(): return {'ok': False, 'erro': 'nao ha chave da Zoo cadastrada (aba Criar peca)'}
            self.zoo.origem = 'api'; self.zoo.auto_mesa = bool(d.get('adicionar_na_mesa', True))
            self.zoo.iniciar(str(d.get('descricao', '')), cfg, None)
        return {'ok': True, 'tarefa': self.zoo.status(), 'chaves': zoo_cad.status_chaves(), 'zoo_exe_encontrado': bool(zoo_cad.achar_cli(cfg)), 'api_autorizada': cfg['permitir_mcp'], 'pecas_criadas': zoo_cad.listar_pecas()[:20]}

    # ---------- diagnostico das pecas da impressora ----------
    def diag_iniciar(self, ids, permitir_aquecer=False, permitir_mover=False, permitir_extrusor=False, origem='tela'):
        """Roda testes_hw.py numa thread. origem 'tela' pergunta ao usuario nos testes que precisam de olho/ouvido; 'api' so devolve 'observar'."""
        if self.imprimindo or self.ocupado: return {'ok': False, 'erro': 'a impressora esta ocupada (imprimindo ou em outro teste)'}
        try: rodar, pular = testes_hw.selecionar(ids, permitir_aquecer, permitir_mover, permitir_extrusor)
        except ValueError as e: return {'ok': False, 'erro': str(e)}
        if not rodar: return {'ok': False, 'erro': 'nenhum teste para rodar: os marcados precisam de permissao (aquecer / mover / extrusor)', 'pulados': pular}
        porta = achar_porta()
        if not porta: return {'ok': False, 'erro': 'Nao achei a impressora (cabo USB / ligada?)'}
        self.ocupado = True; self.parar = False
        self.diag = dict(estado='rodando', origem=origem, resultados=[], atual='', msg='Conectando na impressora...', pulados=pular, inicio=time.time(), pedidos=rodar)
        threading.Thread(target=self._diag_thread, args=(porta, rodar, origem), daemon=True).start()
        return {'ok': True, 'rodando': rodar, 'pulados': pular}

    def _diag_thread(self, porta, ids, origem):
        L = None; d = self.diag
        def progresso(i, est, det):
            d['atual'] = i
            if est == 'rodando': d['msg'] = 'Testando: %s' % next(t['nome'] for t in testes_hw.TESTES if t['id'] == i)
            else: d['resultados'].append(dict(id=i, nome=next(t['nome'] for t in testes_hw.TESTES if t['id'] == i), estado=est, detalhe=det))
        try:
            L = self.abrir(porta)
            c = testes_hw.Contexto(L, parar=lambda: self.parar, ao_ler=self.leitura)
            perguntar = (lambda t: self.no_tk(lambda: messagebox.askyesno('Confirme', t, parent=self), 600)) if origem == 'tela' else None
            res = testes_hw.rodar(c, ids, app=self, perguntar=perguntar, progresso=progresso)
            d['resultados'] = res; d['estado'] = 'pronto'; d['msg'] = ''
            self.say('Diagnostico: %d ok, %d com problema.' % (sum(1 for r in res if r['estado'] == 'ok'), sum(1 for r in res if r['estado'] == 'falha')))
        except SystemExit: d['estado'] = 'erro'; d['msg'] = 'Parado.'
        except Exception as e: d['estado'] = 'erro'; d['msg'] = 'Erro: %s' % e
        finally:
            if L: L.fechar()
            self.ocupado = False

    def api_diagnostico(self, d=None):
        """GET: estado/resultados do ultimo diagnostico + lista de testes. POST {testes: [ids]|'seguros'|'todos', permitir_aquecer, permitir_mover, permitir_extrusor}: comeca."""
        r = {'ok': True}
        if d:
            r = self.diag_iniciar(d.get('testes', 'seguros'), bool(d.get('permitir_aquecer')), bool(d.get('permitir_mover')), bool(d.get('permitir_extrusor')), 'api')
            if not r.get('ok'): return r
        return dict(r, diagnostico={k: v for k, v in self.diag.items() if k != 'inicio'}, testes=[dict(id=t['id'], nome=t['nome'], tipo=t['cat'], o_que_faz=t['desc']) for t in testes_hw.TESTES])

    def api_editar(self, d):
        """Edita uma peca (furo, corte, formas, texto, desenho) e devolve imagem. Ver servidor_rede.py / manual MCP."""
        return self.painel_edit.api(d or {})

    def api_modelar(self, d):
        """Aba Modelar pela rede/MCP: criar e editar pecas por passos (formas, desenho, arredondar, casca, furo...) e VER o resultado. Ver modelar_ui.api."""
        return self.painel_mod.api(d or {})

    def agendar_prev_av(self):
        try: self.painel_av.recarregar()
        except Exception: pass

    def api_avancado(self, d=None):
        """GET mostra; POST muda (mescla por cima do atual). Chaves: ativo, inicio{home,mapa,linha}, fim{...}, ventoinha{modo,pct,camada}, velocidade, fluxo, gcode_antes, gcode_depois, por_camada, fatiador_extra."""
        if d:
            if self.imprimindo: return {'ok': False, 'erro': 'esta imprimindo agora'}
            novo = json.loads(json.dumps(self.av))
            def mescla(a, b):
                for k, v in b.items():
                    if k not in a: continue
                    if isinstance(a[k], dict) and isinstance(v, dict): mescla(a[k], v)
                    else: a[k] = v
            try: mescla(novo, d)
            except Exception as e: return {'ok': False, 'erro': str(e)}
            avm.salvar(novo); limpo = avm.carregar()        # carregar() normaliza e limita os valores
            self.av.clear(); self.av.update(limpo)
            self.after(0, self.agendar_prev_av); self.after(0, self.agendar_refatiar)
        ini, il = avm.inicio(self.av, self.bico, self.mesa, self.bico <= 220)
        return {'ok': True, 'avancado': self.av, 'inicio': ini, 'fim': avm.fim(self.av), 'obs': 'o arquivo carregado e preparado de novo sozinho'}

    def api_gcode(self, comandos, permitir_outros=False):
        """G-code livre (so com a impressora parada): confere cada comando, manda e devolve as respostas."""
        if self.imprimindo or self.ocupado: return {'ok': False, 'erro': 'a impressora esta ocupada'}
        if not comandos or not isinstance(comandos, list) or len(comandos) > 40: return {'ok': False, 'erro': 'mande de 1 a 40 comandos'}
        for c in comandos:
            ok, motivo = avm.gcode_seguro(str(c), permitir_outros)
            if not ok: return {'ok': False, 'erro': motivo, 'comando': str(c)}
        porta = achar_porta()
        if not porta: return {'ok': False, 'erro': 'Nao achei a impressora (cabo USB / ligada?)'}
        self.ocupado = True; L = None; res = []
        try:
            L = self.abrir(porta)
            for c in comandos:
                c = str(c).split(';')[0].strip(); L.tx(c); linhas = []; fim = time.time() + (600 if c.upper().startswith(('G28', 'M109', 'M190')) else 90); ok = False
                while time.time() < fim:
                    l = L.rx()
                    if not l: continue
                    self.leitura(l); linhas.append(l)
                    if l.startswith('ok'): ok = True; break
                    if any(k in l for k in ('Error', 'STOP', 'halted', 'Killed')): break
                res.append({'comando': c, 'ok': ok, 'resposta': linhas[-6:]})
                if not ok: break
            return {'ok': all(r['ok'] for r in res), 'resultados': res}
        except Exception as e: return {'ok': False, 'erro': str(e), 'resultados': res}
        finally:
            if L: L.fechar()
            self.ocupado = False

    def api_suporte(self, d=None):
        """GET (d=None) mostra; POST muda: tipo nenhum|mesa|tudo, estrutura normal|arvore, padrao, densidade, angulo, folga_z, folga_xy, teto."""
        if d:
            if self.imprimindo: return {'ok': False, 'erro': 'esta imprimindo agora'}
            try:
                if 'tipo' in d:
                    t = {'nenhum': SUPORTES[0], 'mesa': SUPORTES[1], 'tudo': SUPORTES[2]}.get(d['tipo'])
                    if not t: return {'ok': False, 'erro': "tipo deve ser 'nenhum', 'mesa' ou 'tudo'"}
                    self.v_sup.set(t)
                if 'estrutura' in d:
                    if d['estrutura'] not in sp.ESTRUTURAS: return {'ok': False, 'erro': "estrutura deve ser 'normal' ou 'arvore'"}
                    self.v_sup_estr.set(d['estrutura'])
                if 'padrao' in d:
                    if d['padrao'] not in sp.PADROES: return {'ok': False, 'erro': 'padrao deve ser um de: ' + ', '.join(sp.PADROES)}
                    self.v_sup_pad_txt.set(sp.PADROES[d['padrao']])
                if 'densidade' in d: self.v_sup_dens.set(int(max(3, min(80, float(d['densidade'])))))
                if 'angulo' in d: self.v_ang.set(int(max(20, min(80, float(d['angulo'])))))
                if 'folga_z' in d: self.v_sup_z.set(max(0.05, min(1.0, float(d['folga_z']))))
                if 'folga_xy' in d: self.v_sup_xy.set(max(0.2, min(3.0, float(d['folga_xy']))))
                if 'teto' in d: self.v_sup_teto.set(bool(d['teto']))
            except (TypeError, ValueError) as e: return {'ok': False, 'erro': 'valor invalido: %s' % e}
        c = self.sup_cfg(); o = self.opcoes_fatiar()
        return {'ok': True, 'tipo': o['suporte'], 'angulo': o['sup_angulo'], 'estrutura': c['estrutura'], 'padrao': c['padrao'], 'densidade': c['dens'], 'folga_z': c['z'], 'folga_xy': c['xy'], 'teto': c['teto'],
                'obs': 'o arquivo carregado e fatiado de novo sozinho depois de mudar (se for STL)'}

    def opcoes_fatiar(self):
        try: ang = int(self.v_ang.get())
        except Exception: ang = 50
        sup = {SUPORTES[0]: 'nenhum', SUPORTES[1]: 'mesa', SUPORTES[2]: 'tudo'}.get(self.v_sup.get(), 'nenhum')
        ades = {ADESOES[0]: 'brim', ADESOES[1]: 'skirt', ADESOES[2]: 'raft'}.get(self.v_ades.get(), 'brim')
        c = self.sup_cfg(); extra = avm.extras_fatiador(self.av['fatiador_extra']) if self.av.get('ativo') else []
        return {'extra_cura': extra, 'suporte': sup, 'sup_angulo': ang, 'adesao': ades, 'sup_estrutura': c['estrutura'], 'sup_padrao': c['padrao'], 'sup_dens': c['dens'], 'sup_z': c['z'], 'sup_xy': c['xy'], 'sup_teto': c['teto']}

    def agendar_refatiar(self):
        """Varias mudancas seguidas (ex.: um modelo de suporte muda 6 campos) viram UM fatiamento so, 0,7 s depois da ultima."""
        if getattr(self, '_ref_id', None):
            try: self.after_cancel(self._ref_id)
            except Exception: pass
        self._ref_id = self.after(700, self.refatiar)

    def refatiar(self):
        self._ref_id = None
        if getattr(self, '_fatiando', False): self._ref_pend = True; return          # ja esta fatiando: refaz quando terminar (nunca dois ao mesmo tempo no mesmo arquivo)
        """Mudou suporte/aderencia: fatia de novo o arquivo carregado (se nao estiver imprimindo)."""
        if self.imprimindo or self.ocupado: return
        orig = getattr(self, 'arq_origem', '')
        if orig and os.path.isfile(orig) and self.arquivo_pronto:
            threading.Thread(target=self.carregar, args=(orig,), daemon=True).start()
        if hasattr(self, 'painel_mesa'): self.painel_mesa.agendar_calculo()

    def usar_mesa(self, stl, n):
        self.say('Mesa 3D: %d peca(s) montadas, fatiando...' % n)
        self.aba('Imprimir')
        threading.Thread(target=self.carregar, args=(stl,), daemon=True).start()

    def receber_arquivo(self, nome, dados):
        if self.imprimindo: return {'ok': False, 'erro': 'esta imprimindo agora'}
        nome = re.sub(r'[^\w.\- ]', '_', os.path.basename(nome)) or 'arquivo'
        if not nome.lower().endswith(('.stl', '.gcode', '.gco')): return {'ok': False, 'erro': 'so STL ou G-code'}
        dest = os.path.join(RECEBIDOS, time.strftime('%Y%m%d_%H%M%S_') + nome)
        open(dest, 'wb').write(dados); self.say('Arquivo recebido pela rede: %s (%d KB)' % (nome, len(dados) // 1024))
        return self.carregar(dest)

    # ---------- impressao ----------
    def imprimir(self):
        if not messagebox.askyesno('Imprimir', 'Impressao de %s.\nBico %d°C, mesa %d°C.\n\nFilamento carregado, mesa limpa e cabo USB ligado?\nComecar?' % (hms(self.total), self.bico, self.mesa)): return
        r = self.iniciar_impressao('tela')
        if not r['ok']: messagebox.showerror('Impressora', r['erro'])

    def iniciar_impressao(self, origem):
        if getattr(self, 'painel_manual', None) and self.painel_manual.conectado: self.painel_manual.desconectar(); self.say('Manual: desconectado para imprimir')
        if self.ocupado: return {'ok': False, 'erro': 'a impressora esta ocupada'}
        if not self.cmds or not self.arquivo_pronto: return {'ok': False, 'erro': 'nenhum arquivo pronto'}
        porta = achar_porta()
        if not porta: return {'ok': False, 'erro': 'Nao achei a impressora. Confira o cabo USB e se ela esta ligada.'}
        try: self.cores.preparar_impressao()
        except Exception as e: return {'ok': False, 'erro': 'Cores: %s' % e}
        self.parar = False; self.imprimindo = True; self.ocupado = True; self.cmds = list(self.cmds)
        self.st.update(etapa=0, msg='Conectando...', bico=0, bico_alvo=self.bico, mesa=0, mesa_alvo=self.mesa, i=0, n=len(self.cmds), t_peca=None, falta=self.total, cam=0, hist=[], fim=None, erro=None, comeco=time.time())
        self.porta_txt = 'Porta ' + porta; self.say('Impressao iniciada (%s)' % origem); self.registrar('inicio')
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        self.parada_tipo = None; self.parada_motivo = ''
        self.pausado = False; self.pausa_pedida = False; self.fw_pausado = False; self.pausa_cam_feita = False; self.continuar_evt.clear(); self.purga_q = []
        self._pos = dict(X=0.0, Y=0.0, Z=0.0, E=0.0, F=1500.0, rel=False, erel=False)
        try: self.pausa_cam = int(self.v_pausa_cam.get()) if self.v_pausa_on.get() else 0
        except Exception: self.pausa_cam = 0
        try: self.runout_on = bool(self.v_runout.get())
        except Exception: self.runout_on = True
        try:
            if self.timelapse.iniciar(self.arquivo): self.say('Time-lapse LIGADO (a cada %s %s)' % (self.timelapse.cfg['cada'], self.timelapse.cfg['modo']))
        except Exception as e: self.say('Time-lapse nao iniciou: %s' % e)
        threading.Thread(target=self.enviar, args=(porta,), daemon=True).start()
        try:
            if self.vigia.iniciar(): self.say('Vigia por camera LIGADO (%s, a cada %s min)' % (vg.PROVEDORES.get(self.vigia.cfg['provedor']), self.vigia.cfg['intervalo_min']))
        except Exception as e: self.say('Vigia nao iniciou: %s' % e)
        return {'ok': True}

    def registrar(self, evento, resultado=''):
        try:
            h = json.load(open(HISTORICO, encoding='utf-8')) if os.path.isfile(HISTORICO) else []
            if evento == 'inicio': h.append(dict(inicio=time.strftime('%d/%m/%Y %H:%M:%S'), arquivo=os.path.basename(self.arquivo), tempo_estimado=hms(self.total), resultado='em andamento'))
            elif h: h[-1].update(fim=time.strftime('%d/%m/%Y %H:%M:%S'), resultado=resultado)
            json.dump(h[-200:], open(HISTORICO, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        except Exception: pass

    def parar_tudo(self):
        self.parar = True
        if self.imprimindo: self.st['msg'] = 'Parando...'

    def fechar(self):
        if self.imprimindo and not messagebox.askyesno('Imprimindo', 'Esta imprimindo. Fechar vai PARAR a impressao. Fechar mesmo?'): return
        self.parar = True; self.alarme['ativo'] = False; self.vigia.encerrar(); self.continuar_evt.set()
        try: self.painel_manual.desconectar(esperar=False)
        except Exception: pass
        self.after(600, self.destroy)

    # ---------- conversa com a impressora ----------
    def leitura(self, l):
        st = self.st
        m = re.search(r'T:([\d.]+)\s*/([\d.]+)', l)
        if m: st['bico'], st['bico_alvo'] = float(m.group(1)), float(m.group(2))
        m = re.search(r'B:([\d.]+)\s*/([\d.]+)', l)
        if m:
            st['mesa'], st['mesa_alvo'] = float(m.group(1)), float(m.group(2))
            if time.time() - getattr(self, '_ult_h', 0) >= 2: self._ult_h = time.time(); st['hist'].append((time.time(), st['bico'], st['mesa']))

    def aguardar(self, L, limite, ignora_parar=False):
        fim = time.time() + limite
        while time.time() < fim:
            if self.parar and not ignora_parar: return 'PARADO'
            if self.fw_pausado and self.continuar_evt.is_set():           # o Victor tocou CONTINUAR depois de uma pausa da propria placa
                L.tx('M108'); self.fw_pausado = False; self.pausado = False; self.continuar_evt.clear(); self._fw_m108 = time.time(); self.st['msg'] = 'Continuando...'; self.say('M108: pedindo para a impressora continuar')
                fim = time.time() + limite
            l = L.rx()
            if not l: continue
            self.leitura(l)
            if self.imprimindo:
                if 'busy' in l: fim = time.time() + limite                  # a placa esta ocupada (M600, espera): nao conta como travada
                self._olhar_firmware(l, L)
                if self.fw_pausado: fim = time.time() + limite
            if l.startswith('ok'): return True
            if any(k in l for k in ('Error', 'STOP', 'halted', 'Killed', 'kill')): return l
        return False

    def abrir(self, porta):
        L = Linha(porta); time.sleep(2.5); L.s.reset_input_buffer()
        for _ in range(60):   # a impressora fica muda um tempo depois de abrir a porta
            if self.parar: raise SystemExit
            L.tx('M105')
            if self.aguardar(L, 4) is True: return L
            self.st['msg'] = 'Aguardando a impressora responder...'
        L.fechar(); raise RuntimeError('A impressora nao respondeu (M105).')

    def z_estado(self, L):
        L.tx('M119'); fim = time.time() + 6; z = None
        while time.time() < fim:
            l = L.rx()
            if 'z_min' in l: z = 'TRIGGERED' if 'TRIGGERED' in l.upper() else 'open'
            if l.startswith('ok'): break
        return z

    def mover_agulha(self, L, s, espera=2.5):
        L.tx('M280 P0 S%d' % s); self.aguardar(L, 5); time.sleep(espera)

    def liberar_sensor(self, L):
        self.mover_agulha(L, 160, 2); self.mover_agulha(L, 90, 1.5)

    def tempo_ate(self, L, comando, esperado, limite=3.0):
        """Manda o comando da agulha e mede em quanto tempo o sinal chega no valor esperado. Devolve segundos ou None."""
        t0 = time.time(); L.tx(comando); self.aguardar(L, 3)
        while time.time() - t0 < limite:
            if self.z_estado(L) == esperado: return time.time() - t0
        return None

    def rodar_sensor(self, L):
        """Testa 6 ciclos desce/sobe (so a agulha, nenhum eixo) e MEDE quanto o sinal demora a acompanhar. O Marlin so espera ~0,5 s: se demorar mais, da 'BLTouch error'.
        Neste firmware: agulha DESCIDA -> 'livre'; RECOLHIDA -> 'acionado'. Devolve (itens, veredito, tudo_ok)."""
        itens = []; self.sensor['itens'] = itens
        z0 = self.z_estado(L)
        itens.append(dict(nome='Agulha recolhida (repouso)', ok=(z0 == 'TRIGGERED'), detalhe='sinal acionado, como deve ser' if z0 == 'TRIGGERED' else 'sinal %s (devia estar acionado)' % z0))
        self.mover_agulha(L, 160, 1.5)   # libera o alarme, se houver
        lentos = 0; falhas = 0; tempos = []
        for k in range(1, 7):
            d = self.tempo_ate(L, 'M280 P0 S10', 'open'); time.sleep(0.6)
            u = self.tempo_ate(L, 'M280 P0 S90', 'TRIGGERED'); time.sleep(0.6)
            ok = d is not None and u is not None
            if d is None or u is None: falhas += 1
            
            if d is not None: tempos.append(d)
            if u is not None: tempos.append(u)
            det = ('desceu e o sinal ficou livre' if d is not None else 'DESCE: NAO RESPONDEU') + ';  ' + ('subiu e o sinal ficou acionado' if u is not None else 'SOBE: NAO RESPONDEU')
            itens.append(dict(nome='Ciclo %d (desce e sobe)' % k, ok=ok, detalhe=det + ''))
        self.mover_agulha(L, 90, 1)
        if not falhas and not lentos:
            v = 'SENSOR OK: nos 6 ciclos a agulha desceu e subiu e o sinal acompanhou. Pode imprimir.'; ok = True
        elif falhas:
            v = ('A AGULHA NAO RESPONDEU em %d de 6 ciclos (o sinal nao acompanhou em 3 s). E isso que causa o erro "BLTouch error". Causa mais provavel: agulha presa por sujeira ou '
                 'azeite que engrossou. Limpe com cotonete e alcool isopropilico e mexa a agulha com o dedo ate correr solta; se nao resolver, o sensor esta com defeito.') % falhas; ok = False
        else:
            v = ('SENSOR LENTO: em %d de 6 ciclos a agulha demorou mais de 0,8 s para acompanhar (maior %.2f s). O Marlin so espera cerca de 0,5 s e da "BLTouch error". '
                 'Provavel agulha pesada (sujeira/azeite). Limpe a agulha com alcool e repita.') % (lentos, max(tempos)); ok = False
        return itens, v, ok

    def sensor_responde(self, L):
        """Checagem rapida antes de esquentar: a agulha tem que descer (sinal livre) e subir (acionado). Tenta liberar o alarme uma vez."""
        for tentativa in range(2):
            self.mover_agulha(L, 160, 1.5); self.mover_agulha(L, 10, 2.5); desce = self.z_estado(L)
            self.mover_agulha(L, 90, 2.5); sobe = self.z_estado(L)
            if desce == 'open' and sobe == 'TRIGGERED': return True
            self.say('Sensor nao respondeu (desce=%s, sobe=%s), tentativa %d' % (desce, sobe, tentativa + 1))
        return False

    def testar_sensor(self):
        if self.ocupado: return {'ok': False, 'erro': 'a impressora esta ocupada'}
        porta = achar_porta()
        if not porta: return {'ok': False, 'erro': 'impressora nao encontrada'}
        self.ocupado = True; self.parar = False; self.sensor.update(rodando=True, itens=[], veredito='Conectando...')
        threading.Thread(target=self._sensor_thread, args=(porta,), daemon=True).start()
        return {'ok': True}

    def _sensor_thread(self, porta):
        L = None
        try:
            L = self.abrir(porta); self.sensor['veredito'] = 'Testando...'
            itens, v, ok = self.rodar_sensor(L); self.sensor['veredito'] = v; self.say('Teste do sensor: ' + ('OK' if ok else 'COM PROBLEMA'))
        except SystemExit:
            self.sensor['veredito'] = 'Teste parado.'
        except Exception as e:
            self.sensor['veredito'] = 'Erro no teste: %s' % e; self.say('Erro no teste do sensor: %s' % e)
        finally:
            if L: L.fechar()
            self.sensor['rodando'] = False; self.ocupado = False

    # ---------- nivelar a mesa (mesa morna) e gravar na memoria da impressora ----------
    def nivelar_agora(self):
        if self.ocupado: messagebox.showinfo('Nivelar', 'A impressora está ocupada agora.'); return
        porta = achar_porta()
        if not porta: messagebox.showerror('Nivelar', 'Não achei a impressora. Confira o cabo USB e se ela está ligada.'); return
        try: temp = max(30, min(100, int(self.v_nivel_temp.get())))
        except Exception: temp = 60
        if not messagebox.askyesno('Nivelar a mesa', 'A impressora vai:\n1. conferir o sensor (só a agulha);\n2. esquentar só a MESA a %d°C e esperar ~3 min;\n3. fazer o Home e medir os pontos da mesa;\n4. GRAVAR o nivelamento na memória dela.\n\nA mesa tem que estar LIVRE (sem peça) e o sensor já lubrificado.\nPode começar?' % temp): return
        self.ocupado = True; self.parar = False
        self.nivel.update(rodando=True, msg='Conectando...', pontos=0, erro='')
        self.say('Nivelamento iniciado (mesa a %d°C)' % temp)
        threading.Thread(target=self._nivelar_thread, args=(porta, temp), daemon=True).start()

    def _espera_ok(self, L, limite, conta=None):
        """Le a impressora ate o 'ok'. 'conta' = trecho de texto que conta como ponto medido."""
        fim = time.time() + limite
        while time.time() < fim:
            if self.parar: raise SystemExit
            l = L.rx()
            if not l: continue
            self.leitura(l)
            if conta and conta in l:
                self.nivel['pontos'] += 1; self.nivel['msg'] = 'Medindo a mesa... %d pontos medidos' % self.nivel['pontos']
            if l.startswith('ok'): return True
            if any(k in l for k in ('Error', 'STOP', 'halted', 'Killed', 'kill')): return l
        return False

    def _nivelar_thread(self, porta, temp):
        n = self.nivel; st = self.st; L = None; deu_certo = False
        st.update(bico_alvo=0, mesa_alvo=temp)
        try:
            L = self.abrir(porta)
            n['msg'] = 'Conferindo o sensor (só a agulha)...'
            if not self.sensor_responde(L):
                raise RuntimeError('O sensor de nivelamento não responde (a agulha não desce/sobe). Nada foi aquecido. Veja a aba Sensor e lubrifique/limpe a agulha.')
            L.tx('M155 S2'); self.aguardar(L, 3)
            n['msg'] = 'Esquentando a mesa até %d°C...' % temp
            L.tx('M140 S%d' % temp); self.aguardar(L, 10)
            L.tx('M190 S%d' % temp)
            r = self._espera_ok(L, 900)
            if r is not True: raise RuntimeError('A mesa não chegou em %d°C: %s' % (temp, r))
            fim_espera = time.time() + self.nivel_espera; ult = 0
            while time.time() < fim_espera:       # deixa o calor se espalhar pela mesa antes de medir
                if self.parar: raise SystemExit
                n['msg'] = 'Mesa em %d°C. Esperando o calor se espalhar: faltam %d s...' % (temp, fim_espera - time.time())
                if time.time() - ult > 5: ult = time.time(); L.tx('M105'); self.aguardar(L, 5)
                time.sleep(1)
            tent = 0
            while True:
                n['msg'] = 'Home (zerando os eixos com o sensor)...'
                L.tx('G28'); r = self._espera_ok(L, 300)
                if r is True:
                    n['pontos'] = 0; n['msg'] = 'Medindo a mesa...'
                    L.tx('G29'); r = self._espera_ok(L, 900, conta='Bed X')
                if r is True: break
                if 'BLTouch' in str(r) and tent < 3 and not self.parar:
                    tent += 1; self.say('Erro do sensor no nivelamento. Tentativa %d de 3...' % tent); n['msg'] = 'Erro do sensor: tentativa %d de 3...' % tent
                    L.tx('M999'); self.aguardar(L, 4); self.liberar_sensor(L); continue
                raise RuntimeError('Parou no nivelamento: %s. Veja protocolo_serial.log' % r)
            n['msg'] = 'Gravando o nivelamento na memória da impressora...'
            L.tx('M500'); r = self._espera_ok(L, 20)
            if r is not True: raise RuntimeError('A impressora não confirmou a gravação (M500): %s' % r)
            L.tx('M420 S1'); self._espera_ok(L, 20)
            L.tx('G91'); self.aguardar(L, 5); L.tx('G1 Z10 F600'); self.aguardar(L, 30); L.tx('G90'); self.aguardar(L, 5)
            hora = time.strftime('%d/%m %H:%M')
            n.update(feito=True, hora=hora, temp=temp, msg='Pronto!', erro='')
            try: json.dump(dict(feito=True, hora=hora, temp=temp, pontos=n['pontos']), open(NIVEL_JSON, 'w', encoding='utf-8'))
            except Exception: pass
            self.say('Nivelamento gravado (%s, mesa %d°C, %d pontos)' % (hora, temp, n['pontos'])); deu_certo = True
        except SystemExit:
            n['msg'] = 'Nivelamento parado.'; self.say('Nivelamento parado pelo usuario')
            try: L.tx('M140 S0')
            except Exception: pass
        except Exception as e:
            n['erro'] = str(e); n['msg'] = 'ERRO: %s' % e; self.say('ERRO no nivelamento: %s' % e)
        finally:
            if L: L.fechar()
            n['rodando'] = False; self.ocupado = False
            if deu_certo or n['erro']:      # mesa fica morna para a proxima impressao; se ninguem imprimir, desliga sozinha em 20 min
                t_ = threading.Timer(1200, self._desligar_se_parado); t_.daemon = True; t_.start()

    def nivel_texto(self):
        n = self.nivel
        if n['rodando']: return n['msg'], AMARELO
        if n['erro']: return n['msg'], VERM
        if n['feito']: return 'Nivelamento gravado em %s (mesa a %d°C). %s' % (n['hora'], n['temp'], 'As próximas impressões vão usá-lo sozinhas enquanto a impressora ficar ligada; se ela for desligada, o programa avisa e usa o sensor de novo.' if self.v_auto_pular.get() else 'A opção automática está desmarcada.'), VERDE
        return 'Nivelamento ainda não feito por aqui. Lubrifique o sensor e clique em NIVELAR AGORA.', DIM

    def enviar(self, porta):
        st = self.st; L = None
        def desligar():
            for c in ('M104 S0', 'M140 S0', 'M107'):
                try: L.tx(c); time.sleep(0.3)
                except Exception: pass
        try:
            L = self.abrir(porta); self.say('Impressora respondeu.')
            st['msg'] = 'Conferindo o sensor (so a agulha)...'   # confere ANTES de esquentar
            pular = False
            try: pular = bool(self.pular_sensor.get())
            except Exception: pass
            auto = False
            try: auto = (not pular) and bool(self.v_auto_pular.get()) and bool(self.nivel.get('feito'))
            except Exception: pass
            if pular or auto:
                L.tx('M119'); z_ok = False; fim_ = time.time() + 6
                while time.time() < fim_:
                    l_ = L.rx()
                    if 'test_axis_known_z_flag' in l_ and 'true' in l_.lower(): z_ok = True
                    if l_.startswith('ok'): break
                if z_ok:
                    pular = True
                    self.cmds = ['G28 X Y' if x == 'G28' else x for x in self.cmds]
                    self.say('Sensor PULADO' + (' (nivelamento de %s)' % self.nivel.get('hora', '') if auto else '') + ': usando a altura e o nivelamento que a impressora ja tem (G28 so em X e Y)')
                elif pular: raise RuntimeError('Nao da para pular o sensor: a impressora nao sabe a altura (Z) dela, provavelmente foi desligada. Desmarque "Pular o sensor" para ela nivelar de novo.')
                else:
                    pular = False; self.say('A impressora foi desligada desde o ultimo nivelamento (perdeu a altura Z): vou usar o sensor normalmente (G28).')
            if not pular and not self.sensor_responde(L):
                raise RuntimeError('O SENSOR DE NIVELAMENTO NAO RESPONDE: a agulha nao desce/sobe como deveria (o sinal nao acompanha). '
                                   'Nada foi aquecido. Veja a aba Sensor: limpe a agulha com cotonete e alcool e mexa ela com o dedo ate correr solta.')
            L.tx('M155 S2'); self.aguardar(L, 3)
            if getattr(self, 'runout_on', True): L.tx('M412 S1'); self.aguardar(L, 5)      # sensor de fim de filamento ligado (se a placa nao conhecer, so responde 'Unknown')
            n = len(self.cmds); ult_m105 = time.time(); cam_ant = -1
            ij = next((x for x, cc in enumerate(self.cmds) if cc == 'M104 S150'), None)
            if ij is not None:   # nao esfria o bico para depois esquentar
                if st['mesa'] >= self.mesa - 10: self.cmds[ij] = 'M104 S%d' % self.bico; self.say('Mesa ja quente: bico vai direto para %d' % self.bico)
                elif st['bico'] > 155: self.cmds[ij] = 'M104 S%d' % min(int(st['bico']), 200); self.say('Bico ja em %d: mantido (sem esfriar)' % st['bico'])
            i = 0; tentativas = 0; ig28 = next((k for k, x in enumerate(self.cmds) if x.startswith('G28')), 0)
            while i < n:
                c = self.cmds[i]
                if self.parar: raise SystemExit
                if i >= self.ini_peca:
                    if self.pausa_pedida: self._pausa(L, 'pedido na tela')
                    elif self.cores.deve_trocar(self.cams[i]): self.cores.trocar(L)
                    elif self.pausa_cam and not self.pausa_cam_feita and self.cams[i] >= self.pausa_cam: self.pausa_cam_feita = True; self._pausa(L, 'camada %d: troca de cor' % self.pausa_cam, 'pausa')
                elif self.pausa_pedida: self.pausa_pedida = False; self.say('Pausa so vale depois que a peca comecar')
                if c.startswith('M190'): st['etapa'], st['msg'] = 1, 'Esquentando a mesa ate %d°C...' % self.mesa
                elif c.startswith('M109'): st['etapa'], st['msg'] = 2, 'Esquentando o bico ate %d°C...' % self.bico
                elif c.startswith('G28'): st['etapa'], st['msg'] = 3, 'Home: zerando os eixos (sensor)...'
                elif c.startswith(('M501', 'M420')): st['etapa'], st['msg'] = 3, 'Carregando o nivelamento salvo...'
                elif i == (self.i_linha if self.i_linha is not None else self.ini_peca - 8): st['etapa'], st['msg'] = 4, 'Fazendo a linha de limpeza...'
                elif i == self.ini_peca: st['etapa'], st['msg'] = 5, 'Imprimindo a peca'; st['t_peca'] = time.time()
                elif c.startswith('M104 S0'): st['etapa'], st['msg'] = 6, 'Finalizando: desligando bico e mesa...'
                L.tx(c); self._rastrear(c)
                r = self.aguardar(L, 900 if c.startswith(('M109', 'M190', 'G28', 'M420', 'M501')) else 60)
                if r is not True and 'BLTouch' in str(r) and i < self.ini_peca and tentativas < 3 and not self.parar:
                    tentativas += 1; self.say('Erro do sensor (%s). Tentativa %d de 3: limpando e refazendo o Home...' % (c, tentativas))
                    st['msg'] = 'Erro do sensor: tentativa %d de 3...' % tentativas; L.tx('M999'); self.aguardar(L, 4); self.liberar_sensor(L); i = ig28; continue
                if r == 'PARADO': raise SystemExit
                if r is not True: raise RuntimeError('Parou na linha %d (%s): %s. Veja protocolo_serial.log' % (i, c, r))
                st['i'], st['n'], st['cam'] = i, n, self.cams[i]
                if st['cam'] != cam_ant: cam_ant = st['cam']; self.timelapse.nova_camada(cam_ant)
                if i >= self.ini_peca and st['t_peca']:
                    dec = time.time() - st['t_peca']; est = self.tempos[i]
                    r_ = min(max(dec / est, 0.8), 1.6) if est > 120 and dec > 120 else 1.0
                    st['falta'] = max(self.total - est, 0) * r_
                if time.time() - ult_m105 > 5:
                    ult_m105 = time.time(); L.tx('M105'); self.aguardar(L, 5); self.timelapse.tick()
                i += 1
            st['etapa'] = 7; st['msg'] = 'TERMINOU! Impressao concluida.'; st['fim'] = time.time(); self.say('FIM')
        except SystemExit:
            tipo = self.parada_tipo
            if tipo and L:      # parada pelo VIGIA: para os movimentos na hora e levanta o bico para nao queimar a peca
                for c_ in ('M410', 'G91', 'G1 Z10 F600', 'G90'):
                    try: L.tx(c_); self.aguardar(L, 20, True)
                    except Exception: pass
            if tipo == 'vigia_manter':
                mins = int(self.vigia.cfg.get('desligar_apos_min', 30) or 0)
                st['msg'] = 'PARADO PELO VIGIA. Temperaturas MANTIDAS' + (' (desligam sozinhas em %d min).' % mins if mins else '.') + ' ' + self.parada_motivo
                self.say('Parado pelo vigia (temperatura mantida)')
                if mins: t_ = threading.Timer(mins * 60, self._desligar_se_parado); t_.daemon = True; t_.start()
            else:
                if L: desligar()
                if tipo: st['msg'] = 'PARADO PELO VIGIA. Bico e mesa desligados. ' + self.parada_motivo; self.say('Parado pelo vigia (esfriando)')
                else: st['msg'] = 'PARADO. Bico e mesa desligados.'; self.say('Parado pelo usuario')
        except Exception as e:
            # NAO esfria em erro (gasta energia para esquentar de novo): mantem bico e mesa. Desliga sozinho em 20 min se ninguem retomar.
            st['erro'] = str(e); st['msg'] = 'ERRO: ' + str(e) + '  (bico e mesa MANTIDOS quentes; desligam sozinhos em 20 min)'; self.say('ERRO: ' + str(e)); self.aviso = str(e)
            t_ = threading.Timer(1200, self._desligar_se_parado); t_.daemon = True; t_.start()
        finally:
            if L: L.fechar()
            try: self.vigia.encerrar()
            except Exception: pass
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            res = 'concluida' if st['etapa'] == 7 else ('erro: ' + st['erro'] if st['erro'] else 'parada')
            self.registrar('fim', res)
            self.imprimindo = False; self.ocupado = False; self.pausado = False; self.fw_pausado = False
            try: self.ao_terminar(res)
            except Exception as e_: self.say('ao_terminar: %s' % e_)

    def ao_terminar(self, res):
        """Depois de cada impressao: time-lapse, rolo, calibracao, fila e aviso no celular."""
        st = self.st; nome = os.path.basename(self.arquivo or '')
        try: self.timelapse.finalizar()
        except Exception: pass
        if res == 'concluida':
            if self.custo_atual:
                try: r = self.rolo.descontar(self.custo_atual['gramas']); self.say('Rolo: -%.0f g, sobram %.0f g' % (self.custo_atual['gramas'], r))
                except Exception: pass
            try: self.painel_fil.marcar_impresso(self.arquivo)
            except Exception: pass
        dur = hms((st['fim'] or time.time()) - st['comeco']) if st.get('comeco') else ''
        if self.fila.estado == 'rodando' and self.fila.atual: self.fila.ao_terminar(res)
        elif res == 'concluida': self.avisar('Impressão de %s CONCLUÍDA (%s).' % (nome, dur), 'terminou')
        elif res.startswith('erro'): self.avisar('ERRO na impressão de %s: %s' % (nome, res[6:][:140]), 'erro', prioridade=1)
        elif self.parada_tipo: pass        # o vigia ja avisou
        self.after(0, lambda: self.atualizar_fila(True))

    # ---------- vigia por camera: alarme e parada ----------
    def vigia_falha(self, r):
        """Chamado pelo vigia (outra thread) quando a IA acha que a impressao deu errado."""
        acao = self.vigia.cfg.get('acao', 'esfriar')
        motivo = 'Vigia: %s. Chance de falha %.0f%%. %s' % (vg.TIPOS.get(r['tipo'], r['tipo']), r['prob'], r.get('motivo', ''))
        self.say(motivo)
        if self.imprimindo:
            self.parada_tipo = 'vigia_manter' if acao == 'manter' else 'vigia_esfriar'; self.parada_motivo = motivo; self.parar = True
        self.avisar('VIGIA: ' + motivo + (' Impressora PARADA e esfriando.' if acao != 'manter' else ' Impressora PARADA, temperatura mantida.'), 'vigia', prioridade=1)
        self.tocar_alarme('IMPRESSÃO COM PROBLEMA', motivo + ('\nImpressora PARADA e esfriando (bico e mesa desligados).' if acao != 'manter' else '\nImpressora PARADA. Temperatura MANTIDA.'))

    def vigia_aviso(self, msg):
        self.say(msg); self.alarme.update(visivel=True, novo=True, titulo='ATENÇÃO', msg=msg)
        try: winsound.Beep(1200, 300)
        except Exception: pass

    def tocar_alarme(self, titulo, msg):
        self.alarme.update(ativo=True, visivel=True, novo=True, titulo=titulo, msg=msg)
        if self.vigia.cfg.get('alarme', True) and not (self._bip and self._bip.is_alive()):
            self._bip = threading.Thread(target=self._bipar, daemon=True); self._bip.start()

    def _bipar(self):
        fim = time.time() + 900
        while self.alarme['ativo'] and time.time() < fim:
            try:
                for f in (1500, 900, 1500, 900):
                    if not self.alarme['ativo']: break
                    winsound.Beep(f, 280)
            except Exception: time.sleep(1)
            time.sleep(0.4)
        self.alarme['ativo'] = False

    def silenciar_alarme(self):
        self.alarme.update(ativo=False, visivel=False)

    def testar_alarme(self):
        self.tocar_alarme('TESTE DO ALARME', 'Este é só um teste do alarme do vigia. Clique em SILENCIAR E FECHAR.')

    def _desligar_se_parado(self):
        """Seguranca: 20 min depois de um erro, se nao ha impressao em andamento, desliga bico e mesa."""
        if self.ocupado or self.imprimindo: return
        try:
            porta = achar_porta()
            if not porta: return
            L = Linha(porta); time.sleep(2.5)
            for c in ('M104 S0', 'M140 S0', 'M107'): L.tx(c); time.sleep(0.4)
            L.fechar(); self.say('Erro antigo: bico e mesa desligados por seguranca (20 min).')
        except Exception: pass

    # ---------- API ----------
    def status_json(self):
        st = self.st; pc = 0.0
        if st['etapa'] >= 5 and st['n']: pc = 100.0 * max(st['i'] - self.ini_peca, 0) / max(st['n'] - self.ini_peca, 1)
        if st['etapa'] == 7: pc = 100.0
        falta = st['falta']
        return dict(ok=True, porta=self.porta_txt, arquivo=os.path.basename(self.arquivo) if self.arquivo else '', info=self.info_txt, pode_imprimir=self.arquivo_pronto and not self.ocupado,
                    imprimindo=self.imprimindo, ocupado=self.ocupado, etapa=st['etapa'], etapa_nome=ETAPAS[st['etapa']] if 0 <= st['etapa'] < 7 else '', msg=st['msg'], erro=st['erro'],
                    bico=st['bico'], bico_alvo=st['bico_alvo'], mesa=st['mesa'], mesa_alvo=st['mesa_alvo'], pct=round(pc, 1), cam=st['cam'], ncam=self.ncam,
                    decorrido=((st['fim'] or time.time()) - st['comeco']) if st['comeco'] else None, falta=falta,
                    termina=time.strftime('%H:%M', time.localtime(time.time() + falta)) if falta is not None else '', tempo_estimado_s=self.total,
                    fila=self.fila.status(), cores=self.cores.status(), pausado=self.pausado, pausa_fw=self.fw_pausado, timelapse=self.timelapse.status(),
                    rolo=dict(nome=self.rolo.d.get('nome'), material=self.rolo.d.get('material'), restam=self.rolo.d.get('gramas_restantes')), custo=self.custo_atual, custo_txt=self.texto_custo(),
                    nivelamento=dict(rodando=self.nivel['rodando'], msg=self.nivel['msg'], feito=self.nivel['feito'], hora=self.nivel['hora'], temp=self.nivel['temp']),
                    vigia=dict(ativo=self.vigia.cfg['ativo'], estado=self.vigia.estado, ultimo=(dict(hora=self.vigia.ultimo['hora'], prob=round(self.vigia.ultimo['prob']), tipo=self.vigia.ultimo['tipo']) if self.vigia.ultimo else None)),
                    sensor=dict(rodando=self.sensor['rodando'], veredito=self.sensor['veredito'], itens=[dict(nome=i['nome'], ok=i['ok'], detalhe=i['detalhe']) for i in self.sensor['itens']]),
                    log=self.logs[-25:], hist=[(round(t - st['hist'][0][0]), b, m) for t, b, m in st['hist'][-120:]] if st['hist'] else [])

    # ---------- tela ----------
    def atualizar(self):
        try:
            st = self.st
            for l in getattr(self, 'pend_log', []):
                self.log.config(state='normal'); self.log.insert('end', l + '\n'); self.log.see('end'); self.log.config(state='disabled')
            self.pend_log = []
            self.lporta.config(text=('● ' + self.porta_txt.replace('Porta ', '')) if self.porta_txt else '○ sem impressora', fg=VERDE if self.porta_txt else DIM)
            self.larq.config(text=os.path.basename(getattr(self, 'larq_txt', '') or '') or 'nenhum arquivo', fg=TXT if getattr(self, 'larq_txt', None) else DIM)
            self.linfo.config(text=self.info_txt, fg=self.info_cor)
            pode = bool(self.arquivo_pronto and not self.ocupado)
            self.bimp.configure(state='normal' if pode else 'disabled', bg=VERDE if pode else '#1C3B30', text='IMPRIMIR' if not self.imprimindo else 'IMPRIMINDO…', disabledforeground='#6FBFA2')
            self.bpar.configure(state='normal' if self.imprimindo else 'disabled')
            self.bescolher.configure(state='disabled' if self.imprimindo else 'normal')
            self.bsens.configure(state='disabled' if self.ocupado else 'normal')
            self.bnivel.configure(state='disabled' if self.ocupado else 'normal')
            self.bpar.configure(state='normal' if (self.imprimindo or self.nivel['rodando']) else 'disabled')
            if self.pausado and not self.imprimindo: self.pausado = False
            tn, cn = self.nivel_texto(); self.lnivel.config(text=tn, fg=cn)
            self.mbico.set(st['bico'], st['bico_alvo']); self.mmesa.set(st['mesa'], st['mesa_alvo'])
            pc = 0
            if st['etapa'] >= 5 and st['n']: pc = 100.0 * max(st['i'] - self.ini_peca, 0) / max(st['n'] - self.ini_peca, 1)
            if st['etapa'] == 7: pc = 100
            self.lpc.set(pc); self.lmsg.config(text=st['msg'], fg=VERM if st['erro'] else (VERDE if st['etapa'] == 7 else TXT))
            w = max(self.barra.winfo_width(), 100); self.barra.delete('all'); self.barra.create_rectangle(0, 0, w * pc / 100, 10, fill=VERDE, outline='')
            if st['comeco'] and st['etapa'] >= 0:
                t = 'Tempo desde o inicio: %s' % hms((st['fim'] or time.time()) - st['comeco'])
                if self.imprimindo and st['etapa'] >= 5 and st['falta'] is not None:
                    t += '   |   Falta ~%s   |   Termina ~%s' % (hms(st['falta']), time.strftime('%H:%M', time.localtime(time.time() + st['falta'])))
                elif self.imprimindo: t += '   |   Peca: ~%s depois de esquentar' % hms(self.total)
                self.ltempo.config(text=t)
            for k, l in enumerate(self.letapas):
                if st['etapa'] > k or st['etapa'] == 7: l.config(text='✔  ' + ETAPAS[k], fg=VERDE)
                elif st['etapa'] == k: l.config(text='▶  ' + ETAPAS[k], fg=AMARELO)
                else: l.config(text='○  ' + ETAPAS[k], fg=DIM)
            self.lcam.config(text=('Camada %d de %d' % (st['cam'], self.ncam)) if st['etapa'] >= 5 and self.ncam else '')
            self.grafico(); self.tela_sensor(); self.atualizar_vigia(); self.painel_cores.atualizar(); self.painel_zoo.atualizar(); self.painel_testes.atualizar()
            self.bpausa.configure(state='normal' if self.imprimindo else 'disabled', text='CONTINUAR' if self.pausado else 'PAUSAR', bg=VERDE if self.pausado else AMARELO, command=self.continuar if self.pausado else self.pausar_agora)
            self.lcusto_imp.config(text=self.texto_custo(), fg=self.cor_rolo() if self.custo_atual else DIM)
            if self.aba_atual == 'Fila': self.atualizar_fila()
            elif self.aba_atual == 'Manual': self.painel_manual.atualizar()
            elif self.aba_atual == 'Filamento': self.painel_fil.atualizar()
            if self.aviso:
                a, self.aviso = self.aviso, None; messagebox.showerror('Erro na impressao', a + '\n\nBico e mesa foram desligados.')
        except Exception as e:
            self.say('tela: %s' % e)
        self.after(500, self.atualizar)

    def tela_sensor(self):
        s = self.sensor
        self.lsv.config(text=('Testando...' if s['rodando'] and not s['itens'] else s['veredito']), fg=VERDE if s['veredito'].startswith('SENSOR OK') else (VERM if s['veredito'].startswith(('SENSOR', 'Erro')) else TXT))
        chave = (len(s['itens']), s['rodando'])
        if chave == getattr(self, '_chave_s', None): return
        self._chave_s = chave
        for w in self.sitens.winfo_children(): w.destroy()
        for i in s['itens']:
            tk.Label(self.sitens, text=('✔  ' if i['ok'] else '✖  ') + i['nome'] + '   —   ' + i['detalhe'], bg=CARD, fg=VERDE if i['ok'] else VERM, font=('Segoe UI', 11), anchor='w').pack(fill='x', pady=2)

    def grafico(self):
        g = self.graf; g.delete('all'); w, h = max(g.winfo_width(), 200), max(g.winfo_height(), 100)
        for v in (0, 50, 100, 150, 200, 250):
            y = h - 18 - (h - 30) * v / 260; g.create_line(40, y, w - 8, y, fill='#263041'); g.create_text(34, y, text=str(v), fill=DIM, anchor='e', font=('Segoe UI', 8))
        hist = self.st['hist'][-300:]
        if len(hist) < 2: g.create_text(w / 2, h / 2, text='(o grafico aparece quando comecar a esquentar)', fill=DIM); return
        t0, t1 = hist[0][0], hist[-1][0]; span = max(t1 - t0, 30)
        for idx, cor in ((1, LARANJA), (2, AZUL)):
            pts = []
            for r in hist: pts += [40 + (w - 48) * (r[0] - t0) / span, h - 18 - (h - 30) * min(r[idx], 260) / 260]
            g.create_line(*pts, fill=cor, width=2, smooth=True)


i18n.instalar_no_app(App)

if __name__ == '__main__':
    App().mainloop()
