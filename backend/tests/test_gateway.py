import sys

import pytest

from studio.infrastructure.agents.hermes_gateway import HermesCliGateway
from studio.shared.application.ports import AgentError
from studio.shared.domain.bots import Bot


def test_ssh_command_quotes_remote_part():
    gw = HermesCliGateway(ssh_target="rises@host", ssh_key="/k")
    cmd = gw.command(Bot.TONTON)
    assert cmd[0] == "ssh" and "rises@host" in cmd and "-i" in cmd
    assert cmd[-1].startswith("docker exec -i hermes sh -c ") and cmd[-1].endswith(" tonton")


def test_local_command_has_no_ssh():
    assert HermesCliGateway().command(Bot.BARU)[:3] == ["docker", "exec", "-i"]


class _EchoGateway(HermesCliGateway):
    """Troca o comando real por um processo local para testar stdin/stdout/erros."""

    def __init__(self, code: str, **kw):
        super().__init__(**kw)
        self._code = code

    def command(self, bot: Bot) -> list[str]:
        return [sys.executable, "-c", self._code]


async def test_ask_pipes_prompt_through_stdin():
    gw = _EchoGateway("import sys; print('eco:' + sys.stdin.read())")
    assert await gw.ask(Bot.TONTON, "olá ção") == "eco:olá ção"


async def test_ask_nonzero_exit_raises():
    gw = _EchoGateway("import sys; sys.stderr.write('boom'); sys.exit(3)")
    with pytest.raises(AgentError, match="boom"):
        await gw.ask(Bot.TONTON, "x")


async def test_ask_timeout_raises():
    gw = _EchoGateway("import time; time.sleep(30)", timeout_s=0.3)
    with pytest.raises(AgentError, match="não respondeu"):
        await gw.ask(Bot.TONTON, "x")


async def test_ask_empty_output_raises():
    gw = _EchoGateway("pass")
    with pytest.raises(AgentError, match="vazio"):
        await gw.ask(Bot.TONTON, "x")


def test_official_tonton_files_are_read_fresh_and_user_text_is_not_shell_code(tmp_path):
    import os
    import subprocess
    soul, memory = tmp_path / 'SOUL.md', tmp_path / 'MEMORY.md'
    soul.write_text('Método oficial de investigação')
    memory.write_text('Regra inicial')
    fake = tmp_path / 'hermes'
    fake.write_text('#!/bin/sh\nprintf "%s" "$4"\n')
    fake.chmod(0o755)
    command = HermesCliGateway().command(Bot.TONTON)
    shell = command[-2].replace('/opt/data/profiles/tonton/SOUL.md', str(soul)).replace('/opt/data/profiles/tonton/memories/MEMORY.md', str(memory))
    env = dict(os.environ, PATH=str(tmp_path)+os.pathsep+os.environ['PATH'])
    prompt = 'Radar; $(touch SHOULD_NOT_EXIST) "texto"'
    first = subprocess.check_output(['sh','-c',shell,'tonton'],input=prompt,text=True,env=env,cwd=tmp_path)
    assert 'Método oficial' in first and 'Regra inicial' in first and prompt in first
    assert not (tmp_path/'SHOULD_NOT_EXIST').exists()
    memory.write_text('Regra atualizada')
    second = subprocess.check_output(['sh','-c',shell,'tonton'],input='Radar',text=True,env=env,cwd=tmp_path)
    assert 'Regra atualizada' in second and 'Regra inicial' not in second
