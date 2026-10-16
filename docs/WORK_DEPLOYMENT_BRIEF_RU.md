# Инструкция ChatGPT Work: развёртывание Contabo + Zomboid + SaaS

**Не утверждай, что развернул сервер, пока не проверил выполнение на VPS.** Ubuntu 24.04.5 LTS, 24 GB RAM (~23 GiB OS), IP 62.171.140.149, IPv6 2a02:c207:2367:882::1, disk ~290 GB; текущий SSH root, Docker не установлен, сервер сообщает reboot required. GitHub SiegerKK/zomboid-server, draft PR #1. Новый мир PZ, ничего не мигрировать.

## Архитектура

1. Отдельные Compose projects `pz` и `saas`, без общих игровых/DB сетей; persistent volumes раздельно.
2. Zomboid UDP 16261/16262 напрямую, RCON 27015 не выставлять в интернет. PZ Java heap 8192m, memory limit 12g, остальные RAM — SaaS и резерв ОС. Закрепить проверенный image digest после теста.
3. Host Nginx — единственный HTTPS ingress для SaaS; `proxy_pass http://127.0.0.1:18080`. SaaS web Nginx в отдельном контейнере и Docker network; API и PostgreSQL на приватных сетях без опубликованных портов. Не настраивать внешнее HTTPS без домена, DNS и TLS. Для разработки допустим SSH tunnel/VPN.
4. SaaS исходников и списка модов ещё нет. Не генерировать за пользователя сам SaaS и не придумывать Workshop IDs.

## Этапы

A. Read-only аудит: hostnamectl; ip -br a; ip route; free -h; df -h; lsblk; ss -tulpen; ufw status verbose; nft list ruleset; systemctl --failed; journalctl -p err -b. Убедиться в Contabo rescue console, сохранить текущую SSH-сессию. Никаких секретов в отчёте.

B. ОС и доступ: завести отдельные Linux аккаунты `kyrylo` и `ihor`, запросив их собственные *публичные* SSH-ключи безопасным способом; персональные home и разрешения. Уточнить, кто имеет sudo. Не давать автоматически обоим sudo или доступ в docker group (эквивалент root). Проверить новый SSH вход отдельно, только затем ограничивать парольный и root login. Патчи безопасности, контролируемый reboot только с rescue доступом; не делать upgrade на Ubuntu 26.04. Согласовать окно и использовать unattended security patches без неожиданных перезагрузок. Проверить IPv4 и IPv6 правила.

C. Docker Engine+Compose: установить из официального Docker apt репозитория под Ubuntu Noble (docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin); не Snap. Проверить daemon, compose, hello-world и автозапуск после reboot. Ограничить journald/container logs и audit disk usage.

D. Firewall: открыть UDP 16261/16262; SSH оставить рабочим. TCP 80/443 только для настроенного SaaS HTTPS или ACME. Никаких публичных 18080, DB, RCON, Docker socket. Помнить, что Docker port publishing может обходить UFW; проверить внешним сканированием IPv4/IPv6.

E. Игра: прочитать draft PR #1. Проверить meshi-team Docker image и Build 42 branch, зафиксировать подходящую версию/digest; запустить vanilla мир с новым паролем, `MAX_PLAYERS=6`, `PUBLIC=false`, `NO_STEAM=0`, `PVP=false`. Отдельные каталоги save/workshop, без `down -v`. Проверить рестарт и прямое подключение по 16262 UDP из двух городов, проехать на машине; собрать RAM, CPU steal, jitter, loss, логи. Список модов получить отдельно; проверить Workshop ID, Mod ID, Build 42, dependencies, maps; update только по согласованию и после backup.

F. SaaS: подготовить отдельный Compose проект, web nginx on `127.0.0.1:18080:80`, backend только внутренний, DB только внутренний. Host nginx proxies to loopback, HTTPS после указания DNS/TLS. Нет SaaS repo, backend runtime, DB, domain => оставить каркас и перечислить ожидаемые решения. Для двух пользователей можно выбрать VPN only до домена.

G. Backups и мониторинг: cold backup мира при остановленной игре, не прерывать игроков без согласования; 7 daily + 4 weekly retention и offsite encrypted store по согласованным реквизитам. Postgres логический pg_dump плюс volumes, restic или аналог, **проверить восстановление**. Monitor VPS disk, memory, swap, OOM, CPU steal, game process, ports, logs, TLS expiration, backup status. Alert channel согласовать.

H. GitHub managed deployment: PR/review -> manual environment approval -> backup -> apply only targeted stack -> health check -> rollback. Dedicated deployment identity, verified SSH known_hosts, no secrets on PR jobs. До создания доступа Work/GitHub к SSH управлять безопасно через Contabo console, поэтапно.

## Запреты и точки остановки

Не передавать пароли, токены, SSH private keys в переписку; доступ через защищённые интеграции Work. Не отключать единственный SSH. Не публиковать Postgres/RCON/Docker socket. Не удалять сохранения или Docker volumes. Не проводить неожиданные reboot или обновления игры/модов. Не выполнять основные обновления Ubuntu. Подтверждать платные сервисы, доступ sudo, домен и публичность SaaS. Если Work не может выполнять команды, сообщить об этом и запросить минимальный bootstrap в console; не симулировать работу.

## Итоговый контроль

Отчёт: команды и проверки фактической версии Ubuntu/Docker/Compose/image digest; пользователи и права; порт-лист IPv4/IPv6; работа PZ и direct UDP; моды; состояние SaaS placeholder vs production; реальные память/CPU; backup + restore; состояние GitHub и неблокирующие зависимости. Следующий шаг — спросить список Workshop и код/домен SaaS, ключи kyrylo/ihor.

Документация: https://docs.docker.com/engine/install/ubuntu/ ; https://docs.docker.com/engine/network/packet-filtering-firewalls/ ; https://github.com/meshi-team/project-zomboid-server .
