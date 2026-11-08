# Caixinha vazada 20x20x1 mm, ABS (bico 245, mesa 100, sem ventoinha), Ender 3 V3 SE
import math
K = 0.42 * 0.2 / (math.pi * 0.875 ** 2)   # mm de filamento por mm de percurso (largura 0,42 / altura 0,2)
g = ['; caixinha teste ABS', 'M413 S0', 'G90', 'M82', 'M140 S100', 'M104 S150', 'M190 S100', 'M109 S245', 'G28', 'M501', 'M420 S1', 'M106 S0', 'G92 E0',
     'G1 Z2 F600', 'G1 X10 Y20 F3000', 'G1 Z0.3 F600', 'G1 X10 Y120 E7 F1000', 'G1 E6.2 F1800', 'G1 Z2 F600', 'G92 E0']
e = [0.0]
def linha(x, y, f):
    global X, Y
    d = math.hypot(x - X, y - Y); e[0] += d * K * f[1]; X, Y = x, y
    g.append('G1 X%.2f Y%.2f E%.4f F%d' % (x, y, e[0], f[0]))
def ir(x, y, z=None):
    global X, Y
    g.append('G1 E%.4f F2100' % (e[0] - 0.8)); g.append('G1 Z%.2f F600' % (z0 + 0.4))
    g.append('G1 X%.2f Y%.2f F6000' % (x, y)); g.append('G1 Z%.2f F600' % z0); g.append('G1 E%.4f F1500' % e[0]); X, Y = x, y
X, Y = 10, 120
x0, y0, s = 105.0, 105.0, 20.0
for camada in range(1, 6):
    z0 = 0.2 * camada
    f = (1200, 1.15) if camada == 1 else (2400, 1.0)
    g.append(';LAYER %d' % camada)
    g.append('G1 Z%.2f F600' % z0)
    ir(x0, y0)
    if camada <= 1:  # base cheia
        y = y0; d = 1
        while y <= y0 + s + 0.01:
            linha(x0 + s if d else x0, y, f); y += 0.42
            if y <= y0 + s + 0.01: linha(x0 + s if d else x0, y, f)
            d = 1 - d
    else:            # parede
        for (x, y) in [(x0 + s, y0), (x0 + s, y0 + s), (x0, y0 + s), (x0, y0)]:
            linha(x, y, f)
g += ['G1 E%.4f F2100' % (e[0] - 1), 'G91', 'G1 Z10 F600', 'G90', 'G1 X10 Y200 F4000', 'M104 S0', 'M140 S0', 'M84 X Y E', 'M105']
open('caixinha_abs.gcode', 'w').write('\n'.join(g) + '\n')
print(len(g), 'linhas; filamento %.1f mm' % e[0])
