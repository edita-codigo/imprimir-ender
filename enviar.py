import serial, serial.tools.list_ports, time, sys
def achar_porta():
    # a impressora (CH340, USB VID 1A86) muda de COM conforme a porta USB; acha sozinho
    for q in serial.tools.list_ports.comports():
        if q.vid == 0x1A86: return q.device
    raise SystemExit('Impressora (CH340) nao encontrada')
s = serial.Serial(achar_porta(), 115200, timeout=1); time.sleep(2.5); s.reset_input_buffer()
log = open('envio.log', 'w', encoding='utf-8')
def p(t): log.write(time.strftime('%H:%M:%S ') + t + '\n'); log.flush()
ult = [0]
def esperar_ok(limite):
    fim = time.time() + limite
    while time.time() < fim:
        l = s.readline().decode(errors='ignore').strip()
        if not l: continue
        if l.startswith('ok'): return True
        if any(k in l for k in ('Error', 'STOP', 'halted', 'Killed', 'kill')): p('ERRO: ' + l); return l
        if l.startswith('T:'):
            if time.time() - ult[0] > 5: ult[0] = time.time(); p('  temp ' + l[:60])
            continue
        if 'busy' in l: continue
        p('  ' + l)
    return False
def desligar():
    for c in ('M104 S0', 'M140 S0', 'M107'): s.write((c + '\n').encode()); time.sleep(0.3)
# pre-checagem do sensor
s.write(b'M280 P0 S160\n'); time.sleep(5); s.write(b'M280 P0 S90\n'); esperar_ok(5); time.sleep(2)
s.write(b'M119\n'); fim = time.time() + 3; z = ''
while time.time() < fim:
    l = s.readline().decode(errors='ignore')
    if 'z_min' in l: z = l.strip()
p('sensor antes: ' + z)
linhas = [l.strip() for l in open(__import__('json').load(open('trabalho.json')).get('arquivo','caixinha_abs.gcode')) if l.strip() and not l.startswith(';')]
for i, c in enumerate(linhas):
    s.write((c + '\n').encode())
    lim = 900 if c.startswith(('M109', 'M190', 'G28', 'G29', 'M420')) else 60
    r = esperar_ok(lim)
    if r is not True:
        p('PAROU na linha %d (%s): %s' % (i, c, r)); desligar(); sys.exit(1)
    if i % 200 == 0 or c.startswith(('M109', 'M190', 'G28', 'G29', 'M420')): p('linha %d/%d: %s' % (i, len(linhas), c))
p('INICIO_IMPRESSAO' if False else 'FIM: impressao enviada por completo')
