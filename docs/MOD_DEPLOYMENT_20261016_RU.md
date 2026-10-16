# Активация модов на основном сервере — 2026-10-16

Этот отчёт уточняет предыдущие записи о vanilla: по прямому разрешению владельца
основной сервер переведён на шесть модов из актуального config/mods.env.
Конфигурация на момент переключения: commit 840e30b5dcaa95dfd496fa955d093357780e2c55.
Последующие изменения документации не требуют перезапуска игры.

## Выполнено и проверено

- ihor добавлен в группу sudo. Пароль учётной записи остаётся locked:
  SSH по персональному ключу сохранён, но password-based sudo требует установки
  личного пароля. NOPASSWD и группа docker не выдавались.
- До остановки RCON показал 0 игроков; выполнены save и quit, выход контейнера 0.
- Холодная копия world-20261016T161108Z.tar.gz: SHA-256 проверен,
  распаковка /var/tmp/pz-restore-check.qG1bNU. Тест boot именно этой новой копии
  не проводился; предыдущая копия уже проходила изолированный boot.
- Основной мир сохранён в /srv/zomboid/data без сброса.
- VPS-only .env (600) выбирает COMPOSE_FILE=compose.yaml:compose.mods.yaml
  и PZ_MODS_FILE=./config/mods.env. Секреты не менялись.
- Workshop snapshot /srv/zomboid/mod-snapshot смонтирован read-only.
  ZombieBuddy JAR скопирован в /srv/zomboid/agent и SHA-256 совпал с аудитом.
  Агент работает только в игровой JVM, policy=deny-new.
- Фактически loading всех шести: ZombieBuddy, Viewpoint, ImmersiveDriving,
  StarlitLibrary, ZomboidForge, TLOU_Infected_42_20.
  Bandits/Creator, клиентские дополнения и альтернативный TLOU MP не включены.
- SERVER STARTED, внутренний RCON отвечает, внешние A2S UDP16261 и RakNet
  UDP16262 отвечают. A2S password_required=0, max_players=6.
- Heap 8192m; лимит 12 GiB; память около 9.23 GiB; OOM=false, restart count=0.
  RCON fps=126 при нуле игроков: это idle sample, не нагрузочный MP-тест.
- Проверка текущих Docker logs: значения ADMIN/RCON/PASSWORD не обнаружены.
- TCP22 доступен; RCON/DB/Redis/Docker API/внутренний nginx снаружи не отвечают.
  Внешняя IPv6-проверка невозможна: у локального клиента нет маршрута IPv6.

## Ограничения и следующие действия

Есть прежние require-предупреждения TLOU/Forge. Серверная загрузка подтверждена,
но поведение infected, совместная езда и клиентские Java-компоненты ещё требуют
двух игроков по docs/MULTIPLAYER_TEST_RU.md. Полная совместимость не объявляется.
Client JAR Viewpoint/Driving не разрешены автоматически dedicated JVM.

Root SSH по паролю оставлен включённым. Перезагрузка пока не выполнена:
владелец разрешил reboot, но ранее не имел Rescue/VNC. Отдельно запрошено
подтверждение риска перезагрузки без проверенной консоли при имеющихся ошибках
cloud-init/networkd-wait-online. Сетевые интерфейсы не изменялись.

Для отката конфигурации .env до модов сохранён root-only
/root/pz-env-before-mods. Не запускать старую vanilla-конфигурацию поверх мира,
уже изменённого модами, без оценки совместимости. При необходимости восстановить
cold backup в НОВЫЙ каталог и переключить PZ_WORLD_DATA_DIR после штатной
остановки; текущие данные не удалять. Не применять автоматический rollback мира.
