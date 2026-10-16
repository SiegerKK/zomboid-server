# Эксплуатация и оставшиеся проверки

Compose-проекты: `pz` и `saas`. Игровые данные: `/srv/zomboid/data`,
Workshop: `/srv/zomboid/workshop`; root-only архивы: `/srv/zomboid/backups`.
Каталог `/srv/pz`, созданный при bootstrap, пока пустой и не используется.

## Первый запуск

Проверить фактическую версию образа и Build 42 до старта. Digest в `.env.example`
фиксирует найденный образ, но не является утверждением об успешном игровом тесте.
Секреты создать только на VPS в `.env` с правами 600. Не выводить `compose config`
без `--quiet`, `docker inspect` окружения и необработанные логи в переписку.
Обёртка startup удаляет известную строку upstream, печатающую пароль администратора.
До создания учётной записи admin пароль передаётся launcher через argv; после
инициализации entrypoint проверяет SQLite whitelist и опускает -adminpassword,
используя сохранённую учётную запись. Поэтому изменение ADMIN_PASSWORD в .env
не является способом ротации уже созданной учётной записи. Ротацию выполнять
отдельно через защищённую административную процедуру игры.
Вывод launcher фильтруется до Docker log driver; конфигуратор печатает только
имена изменённых ключей, без старых/новых значений (это важно при restore,
когда старый RCON-секрет отличается от окружения тестового контейнера).

Запуск: `docker compose config --quiet`, затем `docker compose up -d`.
По умолчанию загружается config/mods.vanilla.env. config/mods.env — staged
кандидат для отдельного теста. Проверить 8192m heap, лимит 12g, PUBLIC=false, MAX_PLAYERS=6,
NO_STEAM=0, PVP=false. Убедиться, что внутри образа нет обновления игры при старте.
Проверить UDP 16261/16262 и реальное подключение двух клиентов, включая поездку
на автомобиле; один UDP-скан не доказывает работоспособность игры.

## Backup и восстановление

Никогда автоматически не останавливать игру с игроками. В согласованное окно:

```bash
python3 scripts/rcon.py zomboid-server players
# Только при players=0 и в согласованное окно:
docker update --restart=no zomboid-server
python3 scripts/rcon.py zomboid-server save
python3 scripts/rcon.py zomboid-server quit
# Дождаться State.Running=false и ExitCode=0; при ошибке не продолжать.
bash scripts/backup.sh
docker compose up -d --force-recreate
bash scripts/restore-check.sh /srv/zomboid/backups/world-TIMESTAMP.tar.gz
```

Не использовать `down -v`. Backup не включает Workshop-кэш; необходимые моды
фиксировать отдельно после согласования. Конфигурация хранится в Git, `.env`
требует отдельной зашифрованной копии. Тест распаковки не заменяет загрузку мира:
запустить копию из временного каталога в изолированном контейнере без публичных
портов и проверить персонажей/мир. Никогда не распаковывать тест поверх live data.
После проверки тестовый каталог удаляет оператор отдельно.

Первая реальная копия: world-20261016T145841Z.tar.gz, около 2.7 MiB.
SHA-256 проверен, распаковка в /var/tmp/pz-restore-check.wNmJQc, все 1886
обычных файлов совпали с архивом побайтно по SHA-256. Для изолированного boot
восстановленной копии используются compose.modtest.yaml, PZ_TEST_DATA и
PZ_TEST_SERVER_NAME=SiegerZomboid. Сети и data основного мира не подключать;
в этом тесте RCON-секрет отдельный, хостовые порты не публикуются.
Восстановленная копия действительно дошла до SERVER STARTED с шестью staged
модами и read-only Workshop; OOM не наблюдался. Игровые персонажи/синхронизация
ещё требуют двух клиентов: отсутствие игроков не заменяет функциональный тест.

WORKSHOP_AUTO_UPDATE=0 проверен в исходниках image helper. Для теста snapshot
Workshop монтируется read-only: при неожиданном обновлении возможен отказ
старта вместо незаметной замены модов. Клиентам нужны совпадающие версии.

## Сбор серверных метрик

Внутренний RCON: python3 scripts/rcon.py zomboid-server 'stats list', затем
'stats performance all'. Helper поддерживает multipart ответы; пароль берётся
из окружения внутри контейнера, не передаётся в argv и не публикуется на host.
Метрики fps, memory-used/max и update-period отделять от клиентских FPS и
реальной нагрузки: 0 игроков и PAUSE_EMPTY=true не являются benchmark.

План retention: 7 daily + 4 weekly. Автоматическое удаление пока не включено;
offsite store, ключ шифрования и окно остановки не согласованы. Не считать local
backup защитой от потери VPS. Для реальной PostgreSQL добавить pg_dump и
изолированный restore test после получения кода/версии СУБД.

## SaaS

`saas/compose.yaml` — отключённый каркас. Web публикуется только на
127.0.0.1:18080, backend должен подключаться к app/database, DB только к database.
Сети не общие с PZ. Host proxy snippet не включается до домена, DNS и TLS.
TCP 80/443 пока не открывать. Нет работающего backend, БД или production HTTPS.

## Управление деплоем

Пока деплой ручной: проверенный commit в PR -> ручное подтверждение -> cold
backup -> применение только нужного Compose-проекта -> health check -> rollback.
Не давать GitHub root SSH. Будущая deployment identity должна иметь отдельный
ключ и ограниченный root-owned wrapper с фиксированным путём и командами;
запись в Compose-файлы, исполняемые через sudo, также эквивалентна root.
Не запускать PR-код с VPS-секретами. Host key брать из проверенной текущей
SSH-сессии, не доверять одному `ssh-keyscan`. Использовать защищённый GitHub
Environment с ручным approval и workflow_dispatch; до настройки этих ограничений
SSH deployment workflow не включать.

Rollback: записать предыдущий commit/digest, остановить только целевой стек,
вернуть конфигурацию и digest. При несовместимом формате мира восстановить
согласованный cold backup в новый каталог, сохранив текущие данные. Никогда не
откатывать базу/мир автоматически через удаление volumes.
