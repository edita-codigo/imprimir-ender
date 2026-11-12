"""Testes da aba Modelar (pytest). Rodar na raiz do repositorio:  python -m pytest tests -v

- test_motor: motor CAD (build123d), sem tela e sem impressora. Sempre roda.
- test_api / test_tela / test_arrastar / test_validar: precisam do programa aberto ou de uma tela;
  so rodam com ENDER_TESTE_COMPLETO=1 (nenhum deles manda nada para a impressora).
"""
import os, subprocess, sys
import pytest

AQUI = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'modelar')
COMPLETO = os.environ.get('ENDER_TESTE_COMPLETO') == '1'


def _rodar(script, timeout=1800):
    r = subprocess.run([sys.executable, '-I', os.path.join(AQUI, script)], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=timeout)
    assert r.returncode == 0, (r.stdout[-3000:] + r.stderr[-1000:])


def test_motor():
    _rodar('t_motor.py')


@pytest.mark.skipif(not COMPLETO, reason='precisa do programa aberto (ENDER_TESTE_COMPLETO=1)')
def test_api():
    _rodar('t_api.py')


@pytest.mark.skipif(not COMPLETO, reason='precisa de tela (ENDER_TESTE_COMPLETO=1)')
@pytest.mark.parametrize('script', ['t_tela.py', 't_arrastar.py', 't_validar.py'])
def test_tela(script):
    _rodar(script)
