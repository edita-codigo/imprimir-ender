"""Time-lapse pela camera (a mesma do vigia): uma foto a cada N camadas ou N minutos, guardadas em timelapse/<data>_<arquivo>/.
No fim monta um video mp4 (ffmpeg via imageio) ou, se nao der, um GIF. Tudo em thread propria: nunca segura a serial."""
import os, io, json, time, threading, glob

PASTA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(PASTA, 'timelapse')
CFG = os.path.join(PASTA, 'timelapse.json')
PADRAO = dict(ativo=False, modo='camadas', cada=2, fps=12, flash=True, max_fotos=1500)
os.makedirs(RAIZ, exist_ok=True)


def carregar_cfg():
    c = dict(PADRAO)
    try: c.update(json.load(open(CFG, encoding='utf-8')))
    except Exception: pass
    return c


def salvar_cfg(c):
    try: json.dump(c, open(CFG, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    except Exception: pass


def montar_video(pasta, fps=12, log=None):
    """Junta os jpg da pasta num mp4 (imageio+ffmpeg). Se nao der, GIF. Devolve o caminho do arquivo gerado ou None."""
    from PIL import Image
    fotos = sorted(glob.glob(os.path.join(pasta, '*.jpg')))
    if len(fotos) < 2: return None
    im0 = Image.open(fotos[0]).convert('RGB'); w, h = im0.size
    w -= w % 2; h -= h % 2                     # o h264 quer medidas pares
    saida = os.path.join(pasta, 'timelapse.mp4')
    try:
        import imageio.v2 as imageio, numpy as np
        with imageio.get_writer(saida, fps=fps, codec='libx264', quality=7, macro_block_size=None, pixelformat='yuv420p') as wr:
            for f in fotos:
                try: wr.append_data(np.asarray(Image.open(f).convert('RGB').resize((w, h))))
                except Exception: continue
        if os.path.getsize(saida) > 1000: return saida
    except Exception as e:
        if log: log('Time-lapse: mp4 falhou (%s), fazendo GIF' % str(e)[:80])
    try:
        saida = os.path.join(pasta, 'timelapse.gif'); esc = min(1.0, 640.0 / w)
        frames = [Image.open(f).convert('RGB').resize((int(w * esc), int(h * esc))).convert('P', palette=Image.ADAPTIVE) for f in fotos[:600]]
        frames[0].save(saida, save_all=True, append_images=frames[1:], duration=int(1000 / max(fps, 1)), loop=0)
        return saida
    except Exception as e:
        if log: log('Time-lapse: GIF tambem falhou (%s)' % str(e)[:80])
        return None


class Timelapse:
    def __init__(self, app):
        self.app = app; self.cfg = carregar_cfg()
        self.pasta = None; self.n = 0; self.pedido = threading.Event(); self.fim = threading.Event(); self.thread = None
        self.ult_cam = -1; self.ult_t = 0; self.estado = 'desligado'; self.video = None; self.msg = ''; self.montando = False; self.ultima_foto = None

    def iniciar(self, nome_arquivo):
        self.cfg = carregar_cfg()
        if not self.cfg.get('ativo'): self.estado = 'desligado'; return False
        base = os.path.splitext(os.path.basename(nome_arquivo or 'peca'))[0][:40]
        self.pasta = os.path.join(RAIZ, time.strftime('%Y%m%d_%H%M_') + base); os.makedirs(self.pasta, exist_ok=True)
        self.n = 0; self.ult_cam = -1; self.ult_t = time.time(); self.video = None; self.msg = ''; self.estado = 'gravando'
        self.pedido.clear(); self.fim.clear()
        self.thread = threading.Thread(target=self._worker, daemon=True); self.thread.start(); return True

    # --- chamadas do laco da impressao (rapidas: so marcam) ---
    def nova_camada(self, cam):
        if self.estado != 'gravando' or cam == self.ult_cam: return
        self.ult_cam = cam
        if self.cfg.get('modo') == 'camadas' and cam % max(1, int(self.cfg.get('cada', 2))) == 0: self.pedido.set()

    def tick(self):
        if self.estado != 'gravando' or self.cfg.get('modo') != 'minutos': return
        if time.time() - self.ult_t >= max(0.5, float(self.cfg.get('cada', 2))) * 60: self.pedido.set()

    def finalizar(self, montar=True):
        if self.estado != 'gravando': return
        self.pedido.set(); self.fim.set(); self.estado = 'montando' if (montar and self.n >= 2) else 'pronto'
        def run():
            if self.thread: self.thread.join(timeout=30)
            if montar and self.n >= 2:
                self.montando = True; self.msg = 'Montando o vídeo (%d fotos)...' % self.n
                self.video = montar_video(self.pasta, int(self.cfg.get('fps', 12)), self.app.say); self.montando = False
                self.msg = ('Vídeo pronto: %s' % os.path.basename(self.video)) if self.video else 'Não consegui montar o vídeo (as fotos estão na pasta).'
                self.app.say('Time-lapse: ' + self.msg)
            else: self.msg = 'Time-lapse com %d foto(s): poucas para um vídeo.' % self.n
            self.estado = 'pronto'
        threading.Thread(target=run, daemon=True).start()

    def _worker(self):
        import vigia
        while not self.fim.is_set():
            if not self.pedido.wait(timeout=1.0): continue
            self.pedido.clear()
            if self.fim.is_set() or self.n >= int(self.cfg.get('max_fotos', 1500)): continue
            try:
                c = dict(self.app.vigia.cfg); c['flash'] = bool(self.cfg.get('flash', True))
                dados = vigia.capturar(c); jpg = vigia.preparar_imagem(dados, max_lado=1280)
                self.n += 1; self.ult_t = time.time(); self.ultima_foto = jpg
                open(os.path.join(self.pasta, '%05d.jpg' % self.n), 'wb').write(jpg)
                self.msg = '%d foto(s)' % self.n
            except Exception as e:
                self.msg = 'foto falhou: %s' % str(e)[:80]

    def status(self):
        return dict(ativo=bool(self.cfg.get('ativo')), estado=self.estado, fotos=self.n, msg=self.msg, video=os.path.basename(self.video) if self.video else None, pasta=os.path.basename(self.pasta) if self.pasta else None)

    def abrir_pasta(self):
        try: os.startfile(self.pasta if self.pasta and os.path.isdir(self.pasta) else RAIZ)
        except Exception: pass
