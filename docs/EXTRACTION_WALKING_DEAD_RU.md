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
первым в Map, upstream добавляет ExtractionMap в spawnregions рядом с обычными городами; для полного цикла выбирать ExtractionMap. Используется pinned 42.22.2
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

На игровом VPS JDK не требуется: Java compiler-only regression пропускается при
отсутствии javac; он выполнен на локальном хосте с JDK. Python/Compose/Workshop
проверки при ручном deploy выполняются на VPS.

## Фактическая установка 11.11.2026

Игровой commit `fad6be876ecfaf0a36926c7ce705f45a3923c9fa`, Build 42.22.2,
активный слот walking_dead, snapshot workshop-20261111T151746Z.
Старая story_test не восстанавливалась и не удалялась. Новые игровые данные
не копировались из неё; использован только полный INI как шаблон конфигурации.

Первый запуск выявил дефект подготовщика: сокращённый INI не позволял upstream
добавить отсутствовавшие Mods/WorkshopItems/RCONPort/RCONPassword. Он сохранён
в отдельном failed-first-boot архиве, исправление не удаляет данные. Полный INI
и повторная копия согласованного пресета исправили запуск. Native RCON использует
порт и пароль; отдельного RCONEnabled в этом INI нет.

| Проверка | Результат |
|---|---|
| Bash smoke на VPS и Python Walking Dead/A-Life/image regressions | PASS; compiler-only Java test пропущен на VPS без javac, выполнен локально |
| 208 Lua файлов/пресет, настоящий Kahlua 42.22.2 | PASS |
| 42 заданных параметра модов: имена, типы и диапазоны | PASS по установленным sandbox-options.txt |
| Фактические Mods, Map, Sleep/PvP/PauseEmpty/PingLimit и Sandbox-файл | PASS |
| A-Life 1.5.1 | PASS: options 683/683, errors=0 |
| Jeem 0.8.0 | PASS: 67 ok, 0 disabled |
| Extraction/A-Life | PASS загрузки: EM-ALIFE module_loaded, ALifeManagement |
| SERVER STARTED и RCON save | PASS, World saved |
| Первый холодный backup walking_dead | PASS: world-20261111T153919Z-1547805.tar.gz, SHA-256 и tar проверены |
| Клиентский TGI Java, обычный пользователь с checksum, полная вылазка и эвакуация | BLOCKED: требуется игровая приёмка |
| Реальная совместная игра двух клиентов, гараж/предметы после эвакуации | BLOCKED: требуется игровая приёмка |

Публично публикуются только UDP 16261/16262. RCON остаётся внутри контейнера.
В логе остаются сообщения ванильной карты (Mannequin zone, basement/metaID);
их нельзя выдавать за отсутствие всех ошибок. Kahlua exceptions новых модов
в просмотренной успешной загрузке не обнаружены.

При подключении выбрать регион **ExtractionMap**. Это существующее имя пункта,
которое создаёт upstream-генератор; он сохраняет также стандартные города.
На клиентах нужны все девять модов профиля, включая TarkovTraders. TGI Java разрешить в ZombieBuddy.
PR не объединять до отдельной клиентской приёмки.

## NPC loot и Tarkov Traders

По запросу владельца: ALife.Drops_WeaponCondition=8 (Serviceable, 6/10),
а не Drops_WeaponChance (шанс выпадения). Родной enum задаёт ступень, не случайный
диапазон. Уже выпавший лут не ремонтируется, существующее оружие NPC может
сохранять ранее выданную прочность/износ; фактическую добычу проверить в игре.
Профиль дополняется Workshop 3811018258 / Mod ID TarkovTraders после ExtractionMode.
Пакет скачивается отдельно с сохранением восьми прежних версий и Steam manifest.

Команда `pz story npc-loot walking_dead --yes` требует чисто остановленную игру,
правильный mount и свежий проверенный cold backup. Меняет ровно один Sandbox-ключ,
обновляет снимок списка модов и готовит новый snapshot; игру не запускает.
`pz story npc-loot walking_dead --audit-traders` экспортирует только публичные
исходники конкретного Workshop-пакета для проверки совместимости, без данных мира.
После проверки: `pz start walking_dead`. Ключ есть также в пресете новых миров.

### Проверено после установки торговцев

Игровой commit e98117978263f94a11bd558dbb16e4040c58051d. Snapshot
workshop-20261111T164715Z; старые восемь пакетов сохранены, скачан только
3811018258. Реальный Mod ID TarkovTraders, версия 2.3.2. Его 14 Lua-файлов
прошли компиляцию настоящим Kahlua 42.22.2. В журнале: Server loaded v2.3.2
и Server features loaded (flea market, discovery, personal items). SERVER STARTED,
RCON и World saved подтверждены; игровая торговля ещё требует клиентской приёмки.
Фактический Sandbox-файл после запуска содержит ALife.Drops_WeaponCondition=8.
Исходная DropPolicy проверена: sandboxRating(8)=6, conditionFor(10,6)=6.
Backup до изменений: world-20261111T164535Z-1601211.tar.gz (SHA-256/tar PASS).

Уточнение лимита: внутренний Population_HostileCeiling подписан автором как
Travelling survivor limit (NPCs) и включает мирных путешественников. Это не
процент враждебных и не население всего округа; существующие отряды не удаляются.
Поддерживаемый диапазон 4–160, штатного unlimited нет. Значение 12 не менялось.

## Отключение Extraction, радиоторговцы

ExtractionMode исключён из MODS. Workshop-пакет остаётся для сохранности и
Steam dependency; его Lua не активен. Map=Muldraugh, KY. Перед JVM fixed guard
восстанавливает 11 реальных стартовых городов после генератора upstream;
действует только на walking_dead без ExtractionMode.
TarkovTraders: TraderAccess=3 (Radio only), TaskSource=2, RadioHideoutOnly=false.
Оружие NPC остаётся на 60%, остальные Sandbox параметры не перезаписываются.

`pz story extraction-off walking_dead` проверяет сохранённые позиции персонажей
через SQLite read-only относительно клеток карты Extraction.
`pz story extraction-off walking_dead --yes` требует чистой остановки, свежего
backup и отсутствия персонажей внутри отключаемой карты. Данные мира и
инвентари не удаляются. Ранее созданные манекены также не удаляются.
Моды walking_dead читаются из per-world mods.env, поэтому Git update сам по
себе не меняет активный набор до явного применения настройки.

### Фактическое отключение Extraction — 2026-11-11

Установлен игровой commit `c1dc11460b667ac64e3598a9b0876e0cdfa44ab6`.
Проверен cold backup `world-20261111T191713Z-1721433.tar.gz` (SHA-256/tar,
30.32 с). Проверка SQLite read-only: один персонаж, вне ExtractionMap.
Мир, инвентари и прогресс сохранены; восстановления не выполнялись.

Выполнено на VPS через ограниченный `pz-vps`:
```bash
pz story extraction-off walking_dead
pz story extraction-off walking_dead --yes
pz start walking_dead
pz story engine-info walking_dead
pz health
pz save-live
```

| Проверка | Результат |
| --- | --- |
| Build 42.22.2, запуск и RCON | PASS; готовность 19:23:56 UTC |
| ExtractionMode отсутствует в активных Mods | PASS; Workshop-пакет сохранён |
| Map=Muldraugh, KY, 11 стандартных стартовых городов | PASS по фактическим файлам |
| TarkovTraders 2.3.2 загружен | PASS по игровому журналу |
| TraderAccess=3, TaskSource=2, RadioHideoutOnly=false | PASS по Sandbox-файлу |
| ALife.Drops_WeaponCondition=8 сохранён | PASS |
| Штатный RCON save | PASS, World saved |
| UDP 16261/16262 IPv4/IPv6, RCON не опубликован | PASS |
| Реальная покупка/продажа и самостоятельные задания | BLOCKED: нужна клиентская приёмка |

Для первой проверки: включить работающую рацию на **101.6 МГц** (Прапор),
контекстное меню **Tarkov Traders radio**. Частота подтверждена TT_Config.lua.
Клиентам оставить TarkovTraders и остальные восемь активных модов профиля;
ExtractionMode больше не активируется сервером.

Не заявляем отсутствие всех ошибок: сохранены ванильные предупреждения
карты/metaID и прежняя ошибка TGI `TGI_SyncServer.lua:19`
(`attempted index: Add of non-table: null`), найденная также в журналах
до отключения Extraction. Совместимость TGI требует отдельной проверки.
Результаты CI не подменялись: установка выполнена разрешённым владельцем
режимом manual-reviewed с локальными и серверными регрессионными проверками.
