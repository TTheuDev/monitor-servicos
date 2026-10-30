# Monitor de Serviços

![Testes](https://github.com/TTheuDev/monitor-servicos/actions/workflows/tests.yml/badge.svg)

Script em Python que verifica se serviços e equipamentos estão no ar, registra o resultado em um log e avisa **quando um serviço cai e quando ele volta**.

Fiz este projeto para praticar monitoramento, automação e tratamento de incidentes, que são tarefas do dia a dia em suporte e infraestrutura. Usa só a biblioteca padrão do Python, então não há nada para instalar.

## O que ele faz

- Checa três tipos de alvo:
  - **ping**: o equipamento responde na rede?
  - **tcp**: a porta está aberta (SSH, DNS, banco de dados...)?
  - **http**: a página responde com o código esperado (200 por padrão)?
- Mede o tempo de resposta de cada checagem.
- Grava tudo em `monitor.log` e mostra na tela.
- Gera um alerta **só quando o estado muda** (caiu / recuperou), para não repetir o mesmo aviso a cada rodada.
- Valida o arquivo de configuração e mostra mensagens de erro claras.
- Modo `--uma-vez` devolve código de saída `1` se algo estiver fora do ar, útil para agendar com cron.

## Como usar

Requisito: Python 3.10 ou superior (os testes automáticos rodam nas versões 3.10 e 3.12).

```bash
git clone https://github.com/TTheuDev/monitor-servicos.git
cd monitor-servicos
cp config.example.json config.json     # edite com os seus alvos
python3 monitor.py                     # roda continuamente (Ctrl+C para parar)
python3 monitor.py --uma-vez           # faz uma rodada e sai
python3 monitor.py -c outro.json       # usa outro arquivo de configuração
```

No Windows, use `py monitor.py` no lugar de `python3 monitor.py`.

Para rodar a cada 5 minutos no Linux, com cron:

```
*/5 * * * * cd /caminho/do/projeto && python3 monitor.py --uma-vez
```

## Configuração

```json
{
  "intervalo_segundos": 30,
  "timeout_segundos": 5,
  "arquivo_log": "monitor.log",
  "alvos": [
    { "nome": "Site", "tipo": "http", "url": "https://exemplo.com", "status_esperado": 200 },
    { "nome": "SSH do servidor", "tipo": "tcp", "host": "192.168.0.10", "porta": 22 },
    { "nome": "Roteador", "tipo": "ping", "host": "192.168.0.1", "timeout": 2 }
  ]
}
```

| Campo | Onde | Descrição |
|---|---|---|
| `intervalo_segundos` | geral | tempo entre as rodadas (padrão 30) |
| `timeout_segundos` | geral | tempo máximo de espera por checagem (padrão 5) |
| `arquivo_log` | geral | onde gravar o log (padrão `monitor.log`) |
| `nome`, `tipo` | cada alvo | obrigatórios; tipo é `ping`, `tcp` ou `http` |
| `host` | ping, tcp | endereço ou IP |
| `porta` | tcp | número da porta |
| `url` | http | endereço completo |
| `status_esperado` | http | código esperado (padrão 200) |
| `timeout` | qualquer alvo | substitui o timeout geral só para esse alvo |

## Exemplo de saída

Teste com um servidor local que foi desligado e ligado de novo:

```
[INFO] OK   Servidor de teste - HTTP 200 (53 ms)
[INFO] OK   Porta do servidor - porta 8765 aberta (1 ms)
[INFO] FALHA Servidor de teste - falha na requisição: <urlopen error [Errno 111] Connection refused> (0 ms)
[WARNING] ALERTA: Servidor de teste fora do ar - falha na requisição: <urlopen error [Errno 111] Connection refused>
[INFO] FALHA Servidor de teste - falha na requisição: <urlopen error [Errno 111] Connection refused> (1 ms)
[INFO] OK   Servidor de teste - HTTP 200 (2 ms)
[WARNING] RECUPERADO: Servidor de teste voltou ao ar
```

Repare que o alerta aparece uma vez, na queda, e não se repete enquanto o serviço continua fora.

## Como o código está organizado

- `checar_tcp`, `checar_http`, `checar_ping`: uma função por tipo de checagem, todas devolvendo `(ok, detalhe)`.
- `executar_checagem`: escolhe a função certa e mede o tempo.
- `validar_config`: confere o JSON antes de começar, para falhar cedo e com mensagem clara.
- `rodada`: percorre os alvos e compara com o estado anterior para decidir se alerta.
- `notificar`: único ponto de aviso. Hoje grava no log; é aqui que entraria e-mail ou Telegram.

## Testes

```bash
python3 -m unittest -v
```

Os testes sobem um servidor HTTP local e cobrem: resposta 200 e 404, status esperado diferente de 200, porta TCP aberta e fechada, validação da configuração e a regra de alertar só na mudança de estado. A checagem por ping usa o comando `ping` do sistema; os testes simulam a saída dele (inclusive o caso do Windows em que o código é 0 mesmo com "host de destino inacessível"), e o ping real foi validado manualmente no Windows.

## Limitações e próximos passos

- Os alertas só vão para o log. Próximo passo: enviar por e-mail ou Telegram dentro de `notificar`.
- As checagens rodam uma de cada vez. Com muitos alvos, vale usar threads ou `asyncio`.
- O ping depende do comando do sistema, e a saída dele varia entre Windows e Linux.
- Não guarda histórico para gráficos. Uma ideia é gravar os tempos de resposta em CSV ou SQLite.
- Um Dockerfile e um serviço `systemd` facilitariam deixar rodando em um servidor.

## O que aprendi

- Diferença entre testar se um host responde (ping), se uma porta está aberta (TCP) e se a aplicação funciona (HTTP).
- Por que alertar só na mudança de estado evita ruído em monitoramento.
- Usar código de saída para integrar um script com agendadores como o cron.
- Escrever testes automatizados com `unittest` e um servidor local de teste.
