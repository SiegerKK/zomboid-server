# SiegerServer: серверный сканер животных без нового клиента

Первая версия подключается только к story_test. Это отдельный серверный
каталог, НЕ Workshop-мод в MODS. SiegerAdmin, SiegerRadio, их клиентские
Lua/JAR и существующий mod list не меняются; DoLuaChecksum остаётся true.

## Почему используется маленький Java-загрузчик

Обычный server Lua в MODS/ванильной папке снова попадает в checksum и
требует клиентский файл. Уже установленный ZombieBuddy предоставляет
`Callbacks.onGameInitComplete.register(Runnable)`: проверенный patch вызывает
его при входе в GameServer.startServer, после LuaManager.finishChecksum.
Наш bootstrap только подписывается на этот callback. **Нет собственного
ClassFileTransformer, ASM, изменения игровых классов/JAR, отключения или
перезаписи checksum.** Новый JAR содержит один наш класс Bootstrap.

Callback проверяет dedicated server, главный игровой поток, checksumDone
и версию42.21, создаёт фиксированные control-файлы с правами0600 и вызывает
нативный LuaManager.RunLua для ЕДИНСТВЕННОГО доверенного пути
`/bootstrap/sieger-server/SiegerServer.lua`. Текст запроса не исполняется.
RunLuaInternal проверен в игровом JAR: чтение/компиляция файла, без addFile
в NetChecksum. Мы не переименовываем модуль в SandboxVars и не меняем
алгоритм проверки. Это root-owned серверный plugin, не клиентский мод.

Lua-модуль регистрирует обычный Events.OnTickEvenPaused callback. При
ошибке bootstrap отключает только новый модуль, а не останавливает игру.
Повторный bootstrap идемпотентен. Обновление Lua-модуля требует серверного
перезапуска в первой версии; hot reload ещё не реализован.

## Сборка и монтирования

```sh
python3 scripts/server_tools_build.py --output server/runtime/SiegerServer.jar
```

Нужен только javac: целевой Java8 bytecode, без игровых/сторонних JAR при
компиляции. CI использует Java17. ZIP timestamps фиксированы и сжатия нет,
но одинаковые байты между разными компиляторами не являются условием работы.
CI отдельно собирает исходник и проверяет поставляемый и собранный JAR на
одном lifecycle-протоколе; оба обязаны содержать только наш Bootstrap.

Compose добавляет два read-only mount: загрузчик и server/lua. Не подменяет
ванильные Lua, TLOU, ZombieBuddy, Radio или список MODS/UDP. В других мирах
активации нет. Ничего из этого не добавляется в клиентский ZIP.

## Команды

```sh
sudo pz story animals snapshot story_test --player admin --radius 100 --yes
sudo pz story animals status story_test
sudo pz story animals report story_test
sudo pz story animals report story_test --output animals-private.json
```

Отчёт: тип, порода (если доступна), animal_id, X/Y/Z, горизонтальное расстояние,
здоровье, dead/baby и age в исходных игровых единицах. Неизвестные поля null.
ID не трактуется как пожизненно уникальный. Радиус1..500; этаж показывается
отдельно, не включается в горизонтальное расстояние.

**Область:** уже загруженные IsoAnimal с ненулевой клеткой. Виртуальные
популяции миграции и животные-предметы в инвентарях, hutch/trailer не входят
в гарантируемое полное поголовье. getAnimals делает один native проход по
objectList, затем обработка ограничена128 животными и примерно2мс на tick.
Максимум10000 объектов, превышение явно error. Поэтапный снимок не атомарен.
Есть inspected/unloaded/errors/elapsed; ошибки сущностей дают partial, не
ложный complete с нулём. В простое — один опрос файла в секунду, не census.

## Приватность и проверка

Фиксированные .txt файлы (native B42 extension allowlist), world/boot/request
identity, TTL30сек, устойчивый replay guard. Один полный JSON плюс newline;
недописанный/чужой ответ CLI не принимает. Файлы заранее созданы bootstrap с
правами0600, native truncate сохраняет права. CLI сверяет активный мир, data,
JAR/Lua mounts, свежесть ready относительно container start и bootUUID.
Результат экспортируется только complete в новый приватный файл вне Git.
Сканы, координаты игроков/баз и сохранения не публикуются.

PASS локально:8 Python/JVM тестов протокола/preview/pending/boot/count,
callback registration, фиксированный путь модуля, неизменность checksum,
права control-файлов; отдельный Lua fixture с моделями животных выполнен
на настоящем B42.21 Kahlua; реальные getter/callback/RunLua ABI проверены
по установленным JAR. Существующие клиентские файлы побайтно неизменны;
Compose/старые Admin тесты проходят.

PENDING: реальный startup/readiness на VPS и animal snapshot, обычный игрок
со СТАРЫМ клиентом и DoLuaChecksum=true, нагрузка большого поголовья.
Администраторский вход и модели этих проверок не заменяют. Старые функции
SiegerAdmin пока не мигрируются. Миры/Workshop не изменяются этим кодом.
