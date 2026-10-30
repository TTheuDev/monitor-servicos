"""Testes do monitor. Rode com: python3 -m unittest -v"""
import http.server
import socket
import threading
import subprocess
import unittest
from unittest import mock

import monitor


class ServidorDeTeste(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        codigo = 200 if self.path == "/ok" else 404
        self.send_response(codigo)
        self.end_headers()

    def log_message(self, *args):  # silencia o log do servidor de teste
        pass


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestChecagens(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = http.server.HTTPServer(("127.0.0.1", 0), ServidorDeTeste)
        cls.porta = cls.servidor.server_address[1]
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def test_http_200_esta_ok(self):
        ok, _ = monitor.checar_http(f"http://127.0.0.1:{self.porta}/ok", 3)
        self.assertTrue(ok)

    def test_http_404_falha(self):
        ok, detalhe = monitor.checar_http(f"http://127.0.0.1:{self.porta}/x", 3)
        self.assertFalse(ok)
        self.assertIn("404", detalhe)

    def test_http_status_esperado_customizado(self):
        ok, _ = monitor.checar_http(f"http://127.0.0.1:{self.porta}/x", 3, status_esperado=404)
        self.assertTrue(ok)

    def test_tcp_porta_aberta(self):
        ok, _ = monitor.checar_tcp("127.0.0.1", self.porta, 3)
        self.assertTrue(ok)

    def test_tcp_porta_fechada(self):
        ok, _ = monitor.checar_tcp("127.0.0.1", porta_livre(), 1)
        self.assertFalse(ok)


def ping_simulado(codigo, saida):
    return subprocess.CompletedProcess(args=["ping"], returncode=codigo, stdout=saida, stderr=b"")


class TestPing(unittest.TestCase):
    def test_windows_com_ttl_esta_ok(self):
        resposta = ping_simulado(0, b"Reply from 192.168.0.1: bytes=32 time=2ms TTL=64")
        with mock.patch("monitor.platform.system", return_value="Windows"), \
             mock.patch("monitor.subprocess.run", return_value=resposta):
            ok, _ = monitor.checar_ping("192.168.0.1", 1)
        self.assertTrue(ok)

    def test_windows_destino_inacessivel_falha_mesmo_com_codigo_zero(self):
        resposta = ping_simulado(0, b"Reply from 192.168.0.5: Destination host unreachable.")
        with mock.patch("monitor.platform.system", return_value="Windows"), \
             mock.patch("monitor.subprocess.run", return_value=resposta):
            ok, _ = monitor.checar_ping("192.168.0.5", 1)
        self.assertFalse(ok)

    def test_linux_codigo_diferente_de_zero_falha(self):
        with mock.patch("monitor.platform.system", return_value="Linux"), \
             mock.patch("monitor.subprocess.run", return_value=ping_simulado(1, b"")):
            ok, _ = monitor.checar_ping("10.0.0.1", 1)
        self.assertFalse(ok)


class TestConfig(unittest.TestCase):
    def test_config_valida_recebe_padroes(self):
        config = monitor.validar_config(
            {"alvos": [{"nome": "x", "tipo": "http", "url": "http://a"}]}
        )
        self.assertEqual(config["intervalo_segundos"], 30)

    def test_sem_alvos_da_erro(self):
        with self.assertRaises(ValueError):
            monitor.validar_config({"alvos": []})

    def test_tipo_invalido_da_erro(self):
        with self.assertRaises(ValueError):
            monitor.validar_config({"alvos": [{"nome": "x", "tipo": "ftp"}]})

    def test_campo_obrigatorio_ausente_da_erro(self):
        with self.assertRaises(ValueError):
            monitor.validar_config({"alvos": [{"nome": "x", "tipo": "tcp", "host": "h"}]})


class TestRodada(unittest.TestCase):
    def test_alerta_so_quando_o_estado_muda(self):
        porta = porta_livre()
        config = monitor.validar_config({
            "timeout_segundos": 1,
            "alvos": [{"nome": "servico", "tipo": "tcp", "host": "127.0.0.1", "porta": porta}],
        })
        estados = {}
        with self.assertLogs("monitor", level="WARNING") as capturado:
            monitor.rodada(config, estados)   # cai: gera alerta
            monitor.rodada(config, estados)   # continua fora: NÃO repete alerta
        alertas = [l for l in capturado.output if "ALERTA" in l]
        self.assertEqual(len(alertas), 1)


if __name__ == "__main__":
    unittest.main()
