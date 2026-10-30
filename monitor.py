#!/usr/bin/env python3
"""Monitor de serviços.

Lê uma lista de alvos em um arquivo JSON, verifica se cada um está no ar
(por ping, porta TCP ou página HTTP), registra tudo em um log e avisa
quando um serviço cai ou volta.

Só usa a biblioteca padrão do Python (nada para instalar).
"""
import argparse
import json
import logging
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

TIPOS_VALIDOS = ("ping", "tcp", "http")
LOG = logging.getLogger("monitor")


# ---------------------------------------------------------------------------
# Checagens: cada função devolve (ok, detalhe)
# ---------------------------------------------------------------------------
def checar_tcp(host, porta, timeout):
    """Tenta abrir uma conexão TCP na porta indicada."""
    try:
        with socket.create_connection((host, porta), timeout=timeout):
            return True, f"porta {porta} aberta"
    except OSError as erro:
        return False, f"falha ao conectar na porta {porta}: {erro}"


def checar_http(url, timeout, status_esperado=200):
    """Faz uma requisição GET e compara o código de status."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resposta:
            status = resposta.status
    except urllib.error.HTTPError as erro:
        # O servidor respondeu, mas com um código de erro (404, 500...).
        status = erro.code
        erro.close()  # libera a conexão, evitando ResourceWarning
    except (urllib.error.URLError, OSError) as erro:
        return False, f"falha na requisição: {erro}"

    if status == status_esperado:
        return True, f"HTTP {status}"
    return False, f"HTTP {status} (esperado {status_esperado})"


def checar_ping(host, timeout):
    """Envia 1 pacote ICMP usando o comando ping do sistema."""
    if platform.system().lower() == "windows":
        comando = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    else:
        comando = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]
    try:
        resultado = subprocess.run(
            comando, capture_output=True, timeout=timeout + 2
        )
    except FileNotFoundError:
        return False, "comando ping não encontrado neste sistema"
    except subprocess.TimeoutExpired:
        return False, "ping excedeu o tempo limite"

    if resultado.returncode != 0:
        return False, "host não respondeu ao ping"
    # No Windows, o ping devolve código 0 até quando o roteador responde
    # "host de destino inacessível". Resposta de verdade traz "TTL=".
    if platform.system().lower() == "windows" and b"ttl" not in resultado.stdout.lower():
        return False, "host inacessível (resposta sem TTL)"
    return True, "host respondeu ao ping"


def executar_checagem(alvo, timeout_padrao):
    """Escolhe a checagem certa para o alvo e mede o tempo de resposta."""
    timeout = alvo.get("timeout", timeout_padrao)
    inicio = time.monotonic()

    if alvo["tipo"] == "tcp":
        ok, detalhe = checar_tcp(alvo["host"], alvo["porta"], timeout)
    elif alvo["tipo"] == "http":
        ok, detalhe = checar_http(
            alvo["url"], timeout, alvo.get("status_esperado", 200)
        )
    else:
        ok, detalhe = checar_ping(alvo["host"], timeout)

    tempo_ms = (time.monotonic() - inicio) * 1000
    return ok, detalhe, tempo_ms


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------
def validar_config(config):
    """Confere se a configuração está correta e devolve com valores padrão."""
    alvos = config.get("alvos")
    if not isinstance(alvos, list) or not alvos:
        raise ValueError("A configuração precisa ter uma lista 'alvos' com ao menos um item.")

    for posicao, alvo in enumerate(alvos, start=1):
        if "nome" not in alvo:
            raise ValueError(f"Alvo #{posicao}: falta o campo 'nome'.")
        tipo = alvo.get("tipo")
        if tipo not in TIPOS_VALIDOS:
            raise ValueError(
                f"Alvo '{alvo['nome']}': 'tipo' deve ser um de {TIPOS_VALIDOS}."
            )
        obrigatorios = {"ping": ["host"], "tcp": ["host", "porta"], "http": ["url"]}
        for campo in obrigatorios[tipo]:
            if campo not in alvo:
                raise ValueError(
                    f"Alvo '{alvo['nome']}' (tipo {tipo}): falta o campo '{campo}'."
                )

    config.setdefault("intervalo_segundos", 30)
    config.setdefault("timeout_segundos", 5)
    config.setdefault("arquivo_log", "monitor.log")
    return config


def carregar_config(caminho):
    with open(caminho, encoding="utf-8") as arquivo:
        return validar_config(json.load(arquivo))


# ---------------------------------------------------------------------------
# Monitoramento
# ---------------------------------------------------------------------------
def configurar_log(arquivo_log):
    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    for destino in (logging.StreamHandler(sys.stdout), logging.FileHandler(arquivo_log, encoding="utf-8")):
        destino.setFormatter(formato)
        LOG.addHandler(destino)


def notificar(mensagem):
    """Ponto único para avisos. Hoje só grava no log.

    Para evoluir o projeto, é aqui que entraria um e-mail, Telegram, etc.
    """
    LOG.warning(mensagem)


def rodada(config, estados):
    """Checa todos os alvos uma vez. Avisa só quando o estado muda.

    `estados` guarda o último resultado de cada alvo (True = no ar).
    Devolve True se todos estiverem no ar nesta rodada.
    """
    tudo_ok = True
    for alvo in config["alvos"]:
        nome = alvo["nome"]
        ok, detalhe, tempo_ms = executar_checagem(alvo, config["timeout_segundos"])
        situacao = "OK  " if ok else "FALHA"
        LOG.info("%s %s - %s (%.0f ms)", situacao, nome, detalhe, tempo_ms)

        anterior = estados.get(nome)
        if not ok and anterior is not False:
            notificar(f"ALERTA: {nome} fora do ar - {detalhe}")
        elif ok and anterior is False:
            notificar(f"RECUPERADO: {nome} voltou ao ar")

        estados[nome] = ok
        tudo_ok = tudo_ok and ok
    return tudo_ok


def monitorar(config, uma_vez=False):
    estados = {}
    if uma_vez:
        return 0 if rodada(config, estados) else 1

    LOG.info("Monitorando %d alvo(s) a cada %ds. Ctrl+C para parar.",
             len(config["alvos"]), config["intervalo_segundos"])
    try:
        while True:
            rodada(config, estados)
            time.sleep(config["intervalo_segundos"])
    except KeyboardInterrupt:
        LOG.info("Monitor encerrado pelo usuário.")
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Monitor simples de serviços.")
    parser.add_argument("-c", "--config", default="config.json",
                        help="arquivo de configuração (padrão: config.json)")
    parser.add_argument("--uma-vez", action="store_true",
                        help="faz uma única rodada e sai (código 1 se algo falhar)")
    args = parser.parse_args(argv)

    try:
        config = carregar_config(args.config)
    except FileNotFoundError:
        print(f"Arquivo '{args.config}' não encontrado. "
              "Copie config.example.json para config.json e ajuste.", file=sys.stderr)
        return 2
    except (ValueError, json.JSONDecodeError) as erro:
        print(f"Configuração inválida: {erro}", file=sys.stderr)
        return 2

    configurar_log(config["arquivo_log"])
    return monitorar(config, uma_vez=args.uma_vez)


if __name__ == "__main__":
    sys.exit(main())
