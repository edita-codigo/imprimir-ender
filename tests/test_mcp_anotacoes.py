"""O servidor MCP precisa dizer, em cada ferramenta, se so le ou se pode causar efeito (readOnlyHint / destructiveHint)."""
import asyncio, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'mcp_ender'))
import server  # noqa: E402

TOOLS = {t.name: t for t in asyncio.run(server.mcp.list_tools())}


def test_todas_tem_anotacao():
    assert len(TOOLS) >= 50
    sem = [n for n, t in TOOLS.items() if t.annotations is None or t.annotations.readOnlyHint is None]
    assert not sem, sem


def test_so_leitura():
    for n in ('ender_status', 'ender_mesa_ver', 'ender_modelar_ver', 'ender_log', 'ender_foto'):
        assert TOOLS[n].annotations.readOnlyHint is True, n


def test_perigosas_marcadas():
    for n in ('ender_imprimir', 'ender_parar', 'ender_gcode', 'ender_purgar', 'ender_mesa_limpar', 'ender_diagnostico'):
        a = TOOLS[n].annotations
        assert a.readOnlyHint is False and a.destructiveHint is True, n


def test_leitura_nao_e_destrutiva():
    for n, t in TOOLS.items():
        if t.annotations.readOnlyHint:
            assert not t.annotations.destructiveHint, n
