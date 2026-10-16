# Фактическое состояние bootstrap, 2026-10-16

Проверено локальным SSH-клиентом на 62.171.140.149; изменения ниже выполнены
на VPS, кроме подготовки Git-конфигурации и защищённых окон на локальном Ubuntu.

## ОС, доступ и безопасность

- Ubuntu 24.04.5 LTS, ядро 6.8.0-139-generic, KVM, 8 vCPU AMD EPYC,
  около 23 GiB RAM, swap нет. Reboot-required: linux-image-6.8.0-147-generic
  и linux-base. Reboot и release-upgrade не выполнялись.
- Rescue/VNC недоступен владельцу; root SSH не отключён, sshd_config и
  действующие сетевые интерфейсы не менялись.
- kyrylo: отдельный ED25519-ключ, home 750, .ssh 700, authorized_keys 600.
  Новый SSH-вход и password-protected sudo (id -u = 0) проверены.
- ihor: отдельный RSA-4096 ключ, аналогичные права, без sudo; пароль заблокирован.
  Вход ihor с собственного компьютера ещё не проверен. Группа docker пуста.
- UFW ACTIVE: deny incoming/routed, allow outgoing. IPv4/IPv6 разрешены только
  TCP/22 и UDP/16261–16262. Включался с systemd rollback на 3 минуты;
  rollback отменён только после НОВОГО SSH-входа kyrylo и проверки sudo.
- docker-ingress-guard active/enabled, правила DOCKER-USER для IPv4/IPv6:
  established/related и игровые UDP разрешены; прочие новые внешние
  подключения к Docker bridges запрещены.
- С локального Ubuntu SSH/22 соединяется; TCP 80/443/27015/5432/6379/2375/2376/
  18080 не отвечает. Внешний IPv6 не проверен: у клиента нет маршрута IPv6.

## Docker и системные службы

- Docker Engine 29.9.1, Compose v5.6.0, containerd и buildx установлены из
  официального Docker apt для Noble. hello-world успешен; Docker/containerd
  active/enabled. Проверка после reboot ещё не выполнялась.
- Docker logging=local, 10m x 3 по умолчанию, live-restore=true. Journald:
  SystemMaxUse=512M, RuntimeMaxUse=128M, MaxRetentionSec=14day.
  Unattended-Upgrade::Automatic-Reboot=false.
- Nginx установлен, active/enabled, nginx -t успешен; default site отключён
  до старта. Ни HTTP/HTTPS, ни SaaS-приложение не опубликованы.
- vps-monitor.timer каждые 5 минут пишет CPU/steal, RAM, диск, контейнеры,
  failed units и последний local backup в /var/log/vps-monitor/latest.txt.
  Внешние оповещения ещё не настроены.
- cloud-init: provider bootcmd завершился exit 1; последняя команда pkill -HUP
  sshd была до генерации host keys. Вероятная причина — отсутствие sshd в этот
  момент; shell tracing не выполнялся. networkd/resolved работают, IPv4/IPv6
  routable/online, но eth0 configuring; wait-online drop-in содержит две
  последовательные ExecStart. Сеть не исправлялась вслепую, ошибки не скрывались.

## Project Zomboid: реальное выполнение

- Закреплён image index digest
  sha256:45c602cb07a1f4b228eefcf92ed4480cf877c409dcd16f0aaa53432063dd3b56.
  Реальный runtime version=42.21.0, baked buildId 25485538, Steam public,
  upstream revision bec4ac61968b5212fe8047185092e19bf194f374.
- Production Compose pz в /opt/zomboid-server; данные /srv/zomboid/data,
  Workshop /srv/zomboid/workshop. Новый vanilla-мир SiegerZomboid создан,
  полностью стартовал и уже пережил save/quit с exit 0 и пересоздание контейнера.
- PASSWORD пустой, PUBLIC=false, NO_STEAM=0, PVP=false, MAX_PLAYERS=6.
  ADMIN_PASSWORD введён защищённо; отдельный случайный RCON-секрет создан
  в памяти локального helper и передан только через SSH stdin.
  Runtime .env root:root/600, секретов в Git/отчёте нет.
- Реальные JVM аргументы -Xmx8192m / -Xms8192m; Docker memory limit 12884901888.
  После создания admin entrypoint опускает пароль в argv. Launcher output
  фильтруется до Docker logs; значения старых/новых настроек не печатаются.
- После первого штатного рестарта с локального Ubuntu получены настоящий
  A2S info UDP/16261 (124 bytes, ~204 ms) и RakNet pong UDP/16262
  (33 bytes, ~244 ms). Это не тест входа двух игровых клиентов.
- Контейнер vanilla наблюдался около 9.1–9.4 GiB RAM, без OOM/авторестартов.
  CPU steal в коротком vmstat sample 0%. Во время загрузки CPU значительно выше;
  клиентские FPS, игровые TPS и синхронизация с двумя игроками ещё не приняты.
- Vanilla тоже выдаёт engine/UI/WorldGen warnings/errors; модовые ошибки
  сравниваются с этой базой, журнал не объявляется полностью чистым.

## Backup и моды

- Два cold backup после players=0, RCON save/quit, State.Running=false/exit 0:
  world-20261016T145841Z.tar.gz и world-20261016T153936Z.tar.gz.
  SHA-256 и распаковка в отдельные /var/tmp/pz-restore-check.* проверены.
  Все 1886 обычных файлов первой распаковки совпали с архивом по SHA-256.
- Копия первого backup запускается отдельно с шестью staged модами,
  отдельной сетью и без host ports; production data не подключён к тесту.
  Результат полного boot этой восстановленной копии ещё фиксируется.
- Все 12 Workshop-позиций из исходного списка сверены с mod.info.
  Death Cam подтверждён: 3816588758 / ViewpointDeathCam.
- В новой версии ветки владелец исключил Bandits2/Creator в пользу TLOU.
  Их файлы сохранены только для аудита; в test snapshot и Mods их нет.
- Шесть выбранных модов реально дошли до SERVER STARTED на новом тестовом
  мире и отвечают RCON, OOM нет. ZombieBuddy 2.3.4 Java agent работает на Linux;
  policy=deny-new блокирует client Java Viewpoint/ImmersiveDriving.
  WARN require TLOU/Forge и реальная MP-работа infected требуют проверки.
- Production остаётся vanilla до решения о совместном MP-тесте.
  Клиентские четыре дополнения в dedicated JVM не включены.
  Альтернативный TLOU_MP 3781448194 проверяется отдельно, не смешивается с original.
- Offsite encrypted storage, retention 7 daily + 4 weekly с удалением,
  оповещения и проверка двух клиентов из Гливице/Львова ещё не настроены.
  Сценарий приёмки: docs/MULTIPLAYER_TEST_RU.md.

GitHub SSH deployment identity/секретов нет. CI только проверяет конфигурации;
автоматический production deploy не включён. SaaS остаётся отключённым каркасом.
