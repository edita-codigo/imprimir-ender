import serial, time
s = serial.Serial('COM7', 115200, timeout=1); time.sleep(3); s.reset_input_buffer()
log = open('nivelar.log', 'w', encoding='utf-8')
def p(t): log.write(time.strftime('%H:%M:%S ') + t + '\n'); log.flush(); print(t, flush=True)
def cmd(c, lim):
    s.write((c + '\n').encode()); fim = time.time() + lim
    while time.time() < fim:
        l = s.readline().decode(errors='ignore').strip()
        if not l or l.startswith('T:'): continue
        p('  ' + l)
        if l.startswith('ok'): return True
        if any(k in l for k in ('Error', 'halted', 'Failed')): return False
    return False
for c, lim in [('M104 S0', 5), ('M140 S0', 5), ('G28', 120), ('G29', 400), ('G1 Z10 F600', 20)]:
    p('>> ' + c)
    if not cmd(c, lim): p('FALHOU em ' + c); break
else: p('NIVELAMENTO OK')
s.close()
