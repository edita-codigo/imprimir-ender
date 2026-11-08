# Painel da impressora: http://localhost:8099 (e http://IP-DO-PC:8099 no celular). Le o envio.log (escrito por enviar.py) e mostra
# temperatura do bico e da mesa, andamento e a camera. API em JSON: /status. Nao abre a porta USB (nao atrapalha a impressao).
import http.server, json, os, re, threading, time

AQUI = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(AQUI, 'envio.log')
HIST = os.path.join(AQUI, 'historico_temperatura.csv')
CAMERA = 'http://192.168.0.50:8081/shot.jpg'


def status():
    st = {'bico': None, 'bico_alvo': None, 'mesa': None, 'mesa_alvo': None, 'linha': None, 'total': None, 'estado': 'sem dados', 'atualizado': None, 'ultimas': []}
    try:
        linhas = open(LOG, encoding='utf-8', errors='ignore').read().splitlines()
    except Exception:
        return st
    st['ultimas'] = linhas[-8:]
    st['atualizado'] = time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(LOG)))
    for l in reversed(linhas):
        m = re.search(r'T:([\d.]+) /([\d.]+) B:([\d.]+) /([\d.]+)', l)
        if m:
            st['bico'], st['bico_alvo'], st['mesa'], st['mesa_alvo'] = (float(x) for x in m.groups()); break
    try:
        tr = json.load(open(os.path.join(AQUI, 'trabalho.json'), encoding='utf-8'))
        st['trabalho'], st['estimado_s'] = tr['nome'], tr['estimado_s']
    except Exception:
        pass
    for l in reversed(linhas):
        m = re.search(r'linha (\d+)/(\d+)', l)
        if m:
            st['linha'], st['total'] = int(m.group(1)), int(m.group(2)); break
    if st.get('estimado_s') and st['linha'] and st['total'] and st['linha'] > 60:
        frac = min(1.0, (st['linha'] - 60) / max(1, st['total'] - 60))
        falta = int(st['estimado_s'] * (1 - frac)); st['falta_s'] = falta
        st['termina_as'] = time.strftime('%H:%M', time.localtime(time.time() + falta))
    ult = ' '.join(linhas[-6:])
    if 'FIM' in ult: st['estado'] = 'TERMINOU'
    elif 'ERRO' in ult or 'PAROU' in ult: st['estado'] = 'PAROU COM ERRO'
    elif st['linha'] is not None and st['linha'] >= 30: st['estado'] = 'IMPRIMINDO'
    elif st['bico'] is not None: st['estado'] = 'ESQUENTANDO / PREPARANDO'
    if time.time() - os.path.getmtime(LOG) > 180 and st['estado'] in ('IMPRIMINDO', 'ESQUENTANDO / PREPARANDO'): st['estado'] += ' (sem novidade ha mais de 3 min)'
    return st


def gravar_historico():
    # a cada 3 s: se o log tem uma temperatura nova, acrescenta (hora;bico;mesa;linha) no CSV, que fica guardado entre impressoes
    ultimo = ''
    while True:
        try:
            st = status()
            for l in reversed(open(LOG, encoding='utf-8', errors='ignore').read().splitlines()):
                if 'T:' in l and 'B:' in l:
                    if l != ultimo and st['bico'] is not None:
                        ultimo = l
                        with open(HIST, 'a', encoding='utf-8') as f:
                            f.write('%s;%s;%s;%s' + chr(10) % (time.strftime('%Y-%m-%d %H:%M:%S'), st['bico'], st['mesa'], st['linha'] if st['linha'] is not None else ''))
                    break
        except Exception:
            pass
        time.sleep(3)


def historico(n=400):
    pts = []
    try:
        for l in open(HIST, encoding='utf-8').read().splitlines()[-n:]:
            d, b, m, ln = (l.split(';') + [''])[:4]
            pts.append([d[11:], float(b), float(m)])
    except Exception:
        pass
    return pts


PAGINA = '''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Impressora</title>
<style>body{font-family:Segoe UI,Arial;background:#101820;color:#fff;margin:0;padding:16px;text-align:center}
.g{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}.c{background:#1c2a38;border-radius:14px;padding:14px 22px;min-width:170px}
.n{font-size:54px;font-weight:700}.s{font-size:15px;color:#9fb3c8}#e{font-size:26px;margin:12px 0;font-weight:700}
.b{height:14px;background:#0b1118;border-radius:8px;margin:8px 0;overflow:hidden}.b i{display:block;height:100%;background:#2ea8ff}
img{max-width:100%;border-radius:12px;margin-top:12px}pre{text-align:left;background:#0b1118;padding:10px;border-radius:10px;font-size:12px;overflow:auto}</style>
<div id=e>...</div><div class=g>
<div class=c><div class=s>BICO</div><div class=n id=bico>-</div><div class=s id=bicoa></div></div>
<div class=c><div class=s>MESA</div><div class=n id=mesa>-</div><div class=s id=mesaa></div></div>
<div class=c><div class=s>ANDAMENTO</div><div class=n id=prog>-</div><div class=b><i id=barra style="width:0"></i></div><div class=s id=lin></div></div>
<div class=c><div class=s>TEMPO</div><div class=n id=tempo style='font-size:34px'>-</div><div class=s id=tempo2></div></div></div><div class=s id=nome></div>
<canvas id=gr width=900 height=260 style='width:100%;max-width:900px;background:#0b1118;border-radius:12px;margin-top:12px'></canvas><div class=s>azul = bico &nbsp; laranja = mesa (historico das ultimas medidas)</div><img id=cam><pre id=log></pre><div class=s id=at></div>
<script>
const f=(v)=>v==null?'-':Math.round(v)+'°';
async function t(){try{const s=await (await fetch('/status')).json();
e.textContent=s.estado;e.style.color=/ERRO/.test(s.estado)?'#ff6b6b':/TERMIN/.test(s.estado)?'#5be37d':'#ffd45e';
bico.textContent=f(s.bico);bicoa.textContent='alvo '+f(s.bico_alvo);mesa.textContent=f(s.mesa);mesaa.textContent='alvo '+f(s.mesa_alvo);
const p=s.total?Math.round(100*s.linha/s.total):0;prog.textContent=p+'%';barra.style.width=p+'%';lin.textContent=s.linha!=null?('linha '+s.linha+' de '+s.total):'';
const h=x=>x==null?'-':Math.floor(x/3600)+'h'+String(Math.floor(x%3600/60)).padStart(2,'0');tempo.textContent=s.falta_s!=null?('falta '+h(s.falta_s)):(s.estimado_s?('total '+h(s.estimado_s)):'-');tempo2.textContent=s.termina_as?('termina ~'+s.termina_as):(s.estimado_s?'estimativa do fatiador':'');nome.textContent=s.trabalho||'';log.textContent=s.ultimas.join('\\n');at.textContent='atualizado '+(s.atualizado||'-')}catch(x){}
cam.src='/camera?'+Date.now();grafico()}
async function grafico(){try{const h=await (await fetch('/historico')).json();const c=gr.getContext('2d');c.clearRect(0,0,900,260);
c.strokeStyle='#223';c.fillStyle='#789';c.font='12px Arial';for(let t=0;t<=250;t+=50){const y=250-t;c.beginPath();c.moveTo(30,y);c.lineTo(900,y);c.stroke();c.fillText(t+'°',2,y+4)}
if(h.length<2)return;const x=i=>30+870*i/(h.length-1);
for(const [k,cor] of [[1,'#2ea8ff'],[2,'#ff9a3c']]){c.strokeStyle=cor;c.lineWidth=2;c.beginPath();h.forEach((p,i)=>{const y=250-Math.min(250,p[k]);i?c.lineTo(x(i),y):c.moveTo(x(i),y)});c.stroke()}
c.fillStyle='#789';c.fillText(h[0][0],30,258);c.fillText(h[h.length-1][0],850,258)}catch(e){}}
t();setInterval(t,4000)</script>'''


class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def do_GET(self):
        if self.path.startswith('/status'):
            body, tipo = json.dumps(status(), ensure_ascii=False).encode(), 'application/json'
        elif self.path.startswith('/historico'):
            body, tipo = json.dumps(historico()).encode(), 'application/json'
        elif self.path.startswith('/camera'):
            try:
                import urllib.request
                body, tipo = urllib.request.urlopen(CAMERA, timeout=6).read(), 'image/jpeg'
            except Exception:
                body, tipo = b'', 'image/jpeg'
        else:
            body, tipo = PAGINA.encode(), 'text/html; charset=utf-8'
        self.send_response(200); self.send_header('Content-Type', tipo); self.send_header('Content-Length', str(len(body))); self.send_header('Cache-Control', 'no-store'); self.end_headers(); self.wfile.write(body)


if __name__ == '__main__':
    threading.Thread(target=gravar_historico, daemon=True).start()
    http.server.ThreadingHTTPServer(('0.0.0.0', 8099), H).serve_forever()
