# Bash-менеджер миров: фактическая установка на VPS, 2026-10-16

Менеджер установлен и проверен на 62.171.140.149. Рабочий слот original
возвращён в фоновый запуск с профилем tlou. Один root-owned репозиторий,
один Bash-менеджер: /usr/local/sbin/pz -> /opt/zomboid-server/pz.
Новых Python-проектов, панелей и дополнительных репозиториев не создавалось.
Код установлен из commit 0c53bd1cebf93cd035e8f06c961f486642fdc238;
последующий commit отчёта изменяет только документацию.

## Ревью и исправления в PR #1

- Менеджер явно выбирает Compose-файлы по профилю. Модовый профиль подключает
  pinned ZombieBuddy agent и read-only snapshot; vanilla не наследует их
  из прежнего COMPOSE_FILE в runtime .env.
- mp-test не подменяет tlou: без отдельного проверенного snapshot его старт
  блокируется. Никаких автоматических скачиваний/обновлений.
- Native RCON CLI получает пароль через приватный tmpfs FIFO с YAML-config,
  без password argv и обычного файла. Ошибки не печатают секрет.
- Stop требует успешного save, затем quit, ждёт завершения с кодом 0.
  При save failure игра остаётся запущенной; forced kill не используется.
- Один flock для операций, проверка фактического data mount против active-world.
  Просмотр logs освобождает lock.
- Import сравнивает фактические Mod ID и Workshop ID в legacy ini с профилем,
  копирует, сохраняет старый каталог. Маркер импорта пишется лишь после
  успешной холодной копии.
- Каждый слот/архив содержит profile, точный mods.env, deployment.txt и data.
  Изменившийся профиль не применяется молча.
- Load проверяет canonical path и SHA именно выбранного архива, отклоняет
  traversal, symlink/hardlink/special members и восстановление поверх слота.
  Архивный mods.env не исполняется.

## Проверки

bash -n pz и sudo bash tests/smoke.sh выполнены на VPS успешно, включая
mock-отказы сохранения/архивации, блокировку, неверный профиль и опасный архив.
GitHub CI code commit 0c53bd1 прошёл: run 38934899456.

Перед остановкой реальный RCON показал 0 игроков. Выполнены save/quit и ExitCode=0.
Legacy cold backup:
- /srv/zomboid/backups/world-20261016T163543Z.tar.gz, SHA-256 проверен;
- распаковка /var/tmp/pz-restore-check.eHSRJJ.

Существующий мир скопирован в /srv/zomboid/worlds/original/data, profile=tlou.
SHA-256 всех 1902 файлов совпали с legacy; общих inode файлов — 0.
Исходный /srv/zomboid/data не удалён и не перемещён.
Исходный набор:
ZombieBuddy;Viewpoint;ImmersiveDriving;StarlitLibrary;ZomboidForge;TLOU_Infected_42_20.
Обе версии TLOU одновременно не включались; Bandits/Creator исключены.

Первая manager cold copy original:
backups/worlds/original/world-20261016T163554Z-6168.tar.gz.

Реально выполнен жизненный цикл с Docker и игрой:
1. create manager-a vanilla, create manager-b vanilla;
2. start manager-a до ответа RCON, save-live;
3. save --yes: clean quit, архив с SHA, restart того же слота до готовности;
4. stop: Running=false, State.Pid=0, ExitCode=0;
5. start manager-b до готовности, проверка отдельной метки данных, stop;
6. start manager-a до готовности: исходная метка сохранена, stop;
7. load архива manager-a в НОВЫЙ manager-restored, профиль и метка совпали;
8. start manager-restored до реального ответа RCON, clean stop;
9. start original до готовности, save-live, status/list.

Архив проверенного save/load:
backups/worlds/manager-a/world-20261016T164213Z-7946.tar.gz.
Все три тестовых слота оставлены, данные/volumes не удалялись.
Перед каждой остановкой в сценарии проверялось 0 игроков.
Метки A/B изолированы, в original их нет.

PAUSE_EMPTY проверен на manager-a и на рабочем original:
по два RCON save с интервалом 35 секунд при 0 игроков; SHA-256 map_t.bin
не менялся. Это проверка остановки игрового времени, не снижения RAM.
Stop отдельно подтверждён отсутствием игрового PID.
Logs проверен с ограниченным viewer: параллельный status выполняется,
viewer завершён timeout=124 без остановки контейнера.

## Итоговое состояние

Активный data mount: /srv/zomboid/worlds/original/data.
Workshop /srv/zomboid/mod-snapshot и agent смонтированы read-only.
Полный SHA-256 manifest Workshop прошёл без изменений: моды не обновлялись.
Heap 8192m, лимит 12 GiB, restart unless-stopped; OOM и самопроизвольных
рестартов нет. Текущая проверка logs не обнаружила значений ADMIN/RCON secrets.
VPS-only .env root:root 600, original parent 700, pz root:root 755;
все пути к исполняемому исходнику защищены от записи обычными пользователями.

Внешние ответы: A2S UDP16261 — 123 bytes, RTT218ms;
RakNet UDP16262 — 33 bytes, RTT74ms. Это разовые запросы, не оценка пинга игры.
A2S players=0/max=6/password_required=0.
TCP22 доступен; RCON, PostgreSQL, Redis, Docker API, внутренний nginx снаружи
не отвечают. Внешняя IPv6-проверка не выполнена: у локального клиента нет маршрута.

Reboot в рамках установки менеджера не выполнялся. Root password SSH,
сетевые интерфейсы, игровой image и версии модов не изменялись.
Мониторинг теперь учитывает вложенные каталоги backup.

## Пользование и границы проверки

sudo pz start [original] — выбор слота/фоновый запуск;
sudo pz stop — полная остановка после подтверждения;
sudo pz save — cold snapshot с подтверждением и возвратом запущенного мира;
sudo pz load — проверенный архив в новый слот;
sudo pz create NAME vanilla|tlou|mp-test;
sudo pz list, sudo pz status, sudo pz logs.

После установки не выполнять прямой Compose up и legacy backup.sh.
Тест подтверждает операции менеджера и boot восстановленного мира,
но не заменяет вход клиентов, проверку персонажей и совместную езду.
Прежние TLOU/Forge warnings и двухклиентская MP-приёмка остаются отдельной
задачей по MULTIPLAYER_TEST_RU.md. Offsite encrypted backups пока не настроены.
