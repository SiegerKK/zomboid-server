# SiegerServer: серверный модуль животных, без нового клиента

Первая версия — opt-in JVM agent `server/runtime/SiegerServer.jar` только для
story_test. Это не Workshop-мод: его нет в MODS/WorkshopItems, media/lua,
SiegerAdmin или клиентском ZIP. Существующий набор клиентских файлов сохраняется.
DoLuaChecksum остаётся включён; checksumDone только читается. Не используются
исключение SandboxVars, отключение проверки, загрузка произвольного Lua/RCON,
правки игровых JAR или новые сетевые порты.

## Подключение

В существующем контейнере нужен закреплённый ZombieBuddy. Собственный agent
запускается перед его transformer и использует только ASM из ZombieBuddy JAR
через локальный Class-Path. Зависимость в агент не копируется. Небольшой JAR
содержит только наши классы; детерминированная сборка:

```sh
python3 scripts/server_tools_build.py --asm-jar /path/to/ZombieBuddy.jar --output server/runtime/SiegerServer.jar
```

Compose добавляет один read-only mount после всех Story/Radio overlays. Для
остальных миров активации нет. `pz` передаёт точное имя story_test. Обновление
Lua/Java/JSON клиентских модов для работы сканера не требуется. Обновление самого
agent требует перезапуска JVM, горячая подмена классов не реализована.

## Точка наблюдения и проверка ABI

Agent добавляет свой callback в начале static `LuaEventManager.triggerEvent`
с первым аргументом String, но работает только на `OnTickEvenPaused`, когда
GameServer.server=true, checksumDone=true и текущий поток равен
GameServer.mainThread. Оригинальная логика событий не заменяется. Это runtime
instrumentation серверного JVM, а не изменение файлов игры.

SHA-256 исходного B42.21 класса LuaEventManager:
`9706f17e9b5e095a0e24230dc944de5d552fa62c997214636c4deb4957cf354b`.
Если класс не совпадает, agent не подключается и не создаёт ready-файл.
Непроверенная новая Build или другой transformer до него не принимаются.
Проверены байткод `IsoWorld.getCell`, `IsoCell.getAnimals`, GameServer getter
игрока, базовые координаты/здоровье и native animal getters. `getAnimals`
создаёт список только из IsoAnimal в objectList, не загружает чанки.
Реальный класс после преобразования прошёл `-Xverify:all` в игровом Java.

## Команды

```sh
sudo pz story animals snapshot story_test --player admin --radius 100 --yes
sudo pz story animals status story_test
sudo pz story animals report story_test
sudo pz story animals report story_test --output animals-private.json
```

Радиус 1..500 клеток, горизонтальное расстояние; этаж каждого животного указан
отдельно. Выдаётся тип, порода (если API вернул её), animal_id, X/Y/Z,
расстояние, здоровье, dead, baby и age в исходных игровых единицах. Неизвестные
необязательные поля — null. animal_id не считается пожизненным уникальным ID.
Статус complete — завершённое серверное наблюдение, не клиентская репликация.

Читаются только уже загруженные мировые IsoAnimal с ненулевой клеткой.
Виртуальные миграционные популяции, предметы-животные в инвентарях и скрытое
содержимое hutch/trailer не объявляются полным поголовьем. Снимок поэтапный,
а не атомарный: до 128 животных / приблизительно 2 мс работы на tick; первая
native выборка `getAnimals` — один проход по objectList. На запрос максимум
10000 ссылок, превышение явно error. Нет фонового сканирования; в простое
одна проверка управляющего файла в секунду. Показаны inspected/errors/unloaded
и продолжительность; ошибки отдельных сущностей дают partial, не ложный ноль.

## Безопасность и приватность

Фиксированные файлы в data/Lua, world/boot/request identity, срок запроса
30 секунд, durable replay guard, проверка symlink/размера, атомарная запись
с правами0600. CLI сверяет выбранный мир, mount data и нашего JAR, время
ready относительно запуска контейнера и boot UUID. Старый ready/ответ после
рестарта не принимается. Экспорт только завершённого результата в новый
приватный файл вне Git; сканы и координаты баз не публикуются.

Игровые объекты, AI, здоровье, мир и checksum сканером не изменяются.
Модуль рассчитан на доверенный root-issued локальный запрос. Клиентские
пакеты, локальные исходные треки и сохранения не входят в PR.

## Статус приёмки

PASS локально: протокол/expiry/boot/pending/preview/JSON, права управляющего
файла, одинаковая сборка с ASM из настоящего ZombieBuddy и публичного
ByteBuddy1.18.8; JVM fixture с моделями объектов: количество/расстояние/replay/
неверный hash; неизменность клиентских Lua; Compose сохраняет прежние mount,
MODS и UDP; инструментация настоящего pinned класса и проверка JVM.

PENDING: реальный startup readiness на VPS, snapshot при подключённом игроке,
фактические животные, ordinary-user вход с прежним клиентом при checksum=true,
нагрузка на большое поголовье. Эти пункты нельзя считать PASS по моделям или
администраторскому входу. До приёмки старые функции SiegerAdmin не переносятся.
