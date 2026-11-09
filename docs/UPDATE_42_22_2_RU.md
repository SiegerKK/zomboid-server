# Обновление story_test до 42.22.2 Stable

Дата подготовки: 2026-11-09. Основа — фактически установленный c11cbec,
без включения ещё не принятой миграции SiegerAdmin из PR #31.

- Steam client build: 26486631, ветка public (локальный appmanifest).
- Steam dedicated build: 26486687, ветка public (OCI labels).
- Образ: ghcr.io/meshi-team/project-zomboid-server@sha256:cec925cd86a7d1d5e020c0c94a30abbf59fd7bc94707fc5649e786d48306898a.
- OCI upstream revision: bec4ac61968b5212fe8047185092e19bf194f374.
- Локальный 42.22.2 projectzomboid.jar SHA-256:
  3c4a7c5f149d784758c6fb5f8fa85f3a21d572e38bc081400e89035f8120d287.

Новый overlay выбирается менеджером только для story_test. Он меняет только
игровой образ и запрещает скрытые автоматические Workshop-обновления:
снимок модов остаётся read-only. Другие миры сохраняют прежний .env image.
Секреты, MODS, сцены, сохранения, volumes, UDP и лимиты RAM не меняются.

Core.getVersion теперь включает git/integrity-диагностику, поэтому bootstrap
использует Core.getGameVersion().toString(), сохраняя fallback для прежнего
42.21 API. Разрешены только прежняя 42.21 и проверяемая точная 42.22.2;
42.22.3/42.23 не разрешаются автоматически. Защита версии не удаляется.

Проверено до установки:
- Публичный образ имеет labels версии 42.22.2 / build 26486687 / public.
- Существуют GameServer.startServer, server/mainThread, LuaManager checksumDone,
  env/platform/RunLua, IsoCell.getAnimals в новом игровом JAR.
- Проверка structured version, старого fallback и отказа неизвестным версиям.
- Compose сохраняет все mounts, MODS, UDP, entrypoint и лимит 12 ГиБ.
- Калькулятор синтаксиса настоящего нового Kahlua компилирует существующий Lua.
- Прежние тесты bootstrap/animal/Compose.

Установка: players=0 → штатный stop → проверенный cold backup → exact CI-passed
commit через pz-deploy → pz start story_test → полный SERVER STARTED + RCON →
pz story engine-info story_test → проверка bootstrap, TLOU registry и ошибок.
При обнаружении несовместимости не отключать checksum/античит и не удалять
данные. Сохранить диагностику и исправить конкретную проблему. Не выполнять
автоматическое восстановление или запуск старой игры на уже обновлённом save.

Игровой вход, радио и два клиента требуют отдельной фактической приёмки.
