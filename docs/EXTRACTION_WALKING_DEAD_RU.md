# Walking Dead / Extraction: новый мир

Новый слот `walking_dead`, отдельные данные; существующий `story_test` сохраняется.
Основа — полный цикл Extraction Mode 0.9.8: одно общее убежище, обычные рейды,
эвакуация, задания и улучшения. Начальная область — Hideout, а не выбор города.
PvP включён на уровне сервера; это не Multi Hideout.

## Настройки владельца

15 ноября, 07:00; 3 месяца после катастрофы, трёхчасовые сутки, холодная погода.
Медленные ходоки, Everyone's Infected. PopulationMultiplier 0.56 вместо 0.80,
Start 0.90 / Peak 1.20. Без ванильного respawn. Боеприпасы 3.0 (Abundant).
Сон разрешён, необязателен. PauseEmpty=true, шесть мест, ping kick выключен.
Пароли и RCON берутся только из существующего VPS-only env.

A-Life + Jeem с поселениями и умеренными осадами; Tactical Grid Inventory
устанавливается на сервер и клиенты, клиентский Java разрешается в ZombieBuddy.
Extraction выбирает NPCProvider=3 (A-Life); историческое имя
EnableBanditsIntegration включает выбранный провайдер, не требует Bandits.
Поздние орды включены, HordeSize=70, эвакуационный ответ 4 зомби/игрока.
Оба процента спринтеров явно нулевые. Остальные опции Extraction — штатные
дефолты, включая спасение персонажа с потерей экипировки при смерти.
Обновление локаций оставлено выключенным (штатный default).
Ни TLOU/Forge, ни SiegerAdmin/Radio не включаются. Старые сцены не копируются.

## Развёртывание

Через штатный ограниченный SSH transport:

```
pz-vps players
pz-vps stop --yes
pz-vps save story_test --yes
pz-vps deploy EXACT_CI_GREEN_COMMIT --yes
pz-vps story alife-install walking_dead --yes
pz-vps start walking_dead
pz-vps health
pz-vps story engine-info walking_dead
pz-vps save-live
```

Подготовка отказывает при существующем слоте, работающем контейнере или отсутствии
свежей проверенной cold backup после остановки story_test. Новые данные не
восстанавливаются из старых. Snapshot копирует проверенные версии шести модов;
скачиваются только TGI и Extraction. ExtractionMap проверяется и добавляется
первым в Map, spawnregions содержит только Hideout. Используется pinned 42.22.2
image и соответствующий ZombieBuddy agent. Никаких reboot, удаления сохранений,
замены секретов или автоматических восстановлений.

## Проверки

До установки: Python regression tests и полный CI; 208 Lua файлов TGI/Extraction
и пресет прошли компиляцию настоящим Kahlua установленной 42.22.2.
Это не подтверждает runtime API и клиентскую синхронизацию.
После запуска нужны SERVER STARTED, RCON, фактические Mods/Map/Sandbox,
отсутствие Lua exceptions новых модов и успешное сохранение.
Клиентская приёмка: старт в убежище, инвентарь/обыск, готовность двух игроков,
вылазка, NPC, эвакуация, сохранение лута и обновление убежища.
До этой проверки полный игровой цикл имеет статус BLOCKED (ожидает игроков).

## Явный ручной deploy при недоступном CI

Владелец разрешил режим без обязательного GitHub Actions после повторного сбоя
DNS Ubuntu mirror в runner. Root-owned helper из `ops/pz-codex-deploy.py`
устанавливается администратором один раз; общие sudo-права codex-pz не выдаются.

`pz-vps deploy EXACT_SHA --yes --manual-reviewed` явно выбирает ручную проверку.
Чистая остановка, свежий SHA-256 cold backup, защищённые пути и точный Git commit
остаются обязательными. После checkout выполняются Bash syntax, offline smoke,
Python regressions Walking Dead/A-Life/image; при ошибке игра остаётся остановленной.
Режим сохраняется в root-owned DEPLOYED_VALIDATION.json и системном журнале.
Без этого флага по-прежнему требуется успешный GitHub Actions.
Локальный Kahlua syntax и реальный игровой запуск дополняют эти проверки.
