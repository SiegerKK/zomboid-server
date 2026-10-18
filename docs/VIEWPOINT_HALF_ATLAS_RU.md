# SiegerViewpointHalf 0.1.0: локальный клиентский Half для актуальных атласов

Статус: **CLIENT TEST**, игровая визуальная и multiplayer-приёмка ещё не выполнены.
Steam-файлы, установленный Viewpoint, VPS, Workshop и сохранения не меняются.

## Причина неработающей галки

В установленном Build 42.21.0 `Core.getOptionTexture2x()` всегда возвращает true,
а setter сообщает `1x textures are disabled.`. Viewpoint 0.1.6.1 на старте
синхронизирует свою галку с этим getter. В старом `Tiles1x.pack` 16220 имён,
в текущем `Tiles2x.pack` 35746, из них 21513 отсутствуют в первом пакете.
Поэтому патч **не** меняет getter/Core.tileScale, не включает старую ветку 1x
и не подменяет современные пакеты неполными старыми ресурсами.

## Реализация

Отдельный Java-only клиентский мод `SiegerViewpointHalf` использует ZombieBuddy.
Зависимость на Viewpoint транзитивно включает ZombieBuddy; мод заявляет
`ZBVersionMin=2.3.0`, `javaJarFile` и `javaPkgName`.

Генератор локально обрабатывает текущие `Tiles2x`, `Tiles2x.floor`, `Overlays2x`,
`Overlays2x.floor`, `JumboTrees2x`, `JumboTreesBigs2x`. UI, часы, depth maps,
B42ChunkCaching и текстуры других модов остаются оригинальными.
Форматы PZPK v1 и legacy PNG v0 читаются без запуска игры. Изображения
дополняются прозрачностью до исходного power-of-two hardware canvas, затем
уменьшаются вдвое с premultiplied-alpha BOX фильтром. Это учитывает реальные
нечётные размеры PNG (например 1018×859): уменьшать их до 509×429 неверно,
так как игровые UV рассчитаны относительно hardware canvas 1024×1024.

На владельческой установленной версии получено **546 страниц**. Расчётный
несжатый базовый RGBA-слой всех выбранных страниц: **2165 → 541.25 МиБ**.
Это НЕ замер фактически занятой VRAM и НЕ обещание экономии 1624 МиБ:
страницы загружаются по необходимости, драйвер сжимает их, существуют mipmaps,
собственные Viewpoint floor pages, FBO и другие ресурсы, которые мод не уменьшает.

Хуки:

1. После штатного `FileTask_LoadPackImage.call()` заменяются только пиксельные
   mip-уровни ImageData на локально подготовленную Half-страницу. Исходные
   размеры, координаты текстур, список ресурсов и full-resolution picking mask
   сохраняются. Mip-цепочку подготавливает настоящая ImageData игры.
2. Оригинальный `TextureID.generateHwId()` загружает уменьшенные mip-уровни;
   расчёты UV и размеры спрайтов остаются исходными 2x. Собственного GL uploader
   для обычного пути нет.
3. Для редкого `TextureID.getData()` компактное GPU-чтение расширяется до
   логического stride в уже выделенном игровом буфере. Это необходимо для
   потребителей пикселей, ожидающих исходную геометрию.
4. Если другой мод записывает `TextureID.setData()` в уменьшенную статическую
   страницу, эта страница переводится обратно в Full и mipmaps пересоздаются.
   Так логическая запись не выходит за физические границы Half-текстуры.
5. Только `viewpoint.platform.GameTextures.follow()` получает адаптер галки.
   Настройка хранится отдельно: `Zomboid/sieger-viewpoint-half.properties`,
   `enabled=true/false`. Half включён по умолчанию для этого тестового пакета.
   Выбор применяется **после полного перезапуска клиента**, текущая сессия
   не переключает уже загруженные текстуры. Tooltip сообщает об этом.

`Default`/`Vivid` не выбирают устаревшие пакеты 1x: мод работает на уровне
источника атласов до шейдерного пакета. Визуальная совместимость с обоими
режимами всё равно требует клиента; это ещё не PASS.

## Защита и ограничения

- SHA-256 game JAR и Viewpoint JAR вшиты в собранный Java-мост; дополнительно
  проверяются оригинальные выбранные packs, отсутствие их подмены через ZFS,
  принадлежность манифеста сборке и SHA-256 каждой загружаемой Half-страницы.
- Несовпадение сборки отключает адаптер, повреждённая страница остаётся Full.
  Следить за `DISABLED` и `FULL fallback` в console.txt; галка сама по себе
  не доказывает, что все страницы были уменьшены.
- `pages` и `uploaded_baseRGBA_reduction_MiB` в логе — **накопленные загрузки**,
  а не число живых страниц/текущая экономия VRAM. Повторные загрузки учитываются
  повторно; освобождение и promotion не делают этот счётчик текущим расходом.
- Штатный worker сначала декодирует исходную страницу и готовит её mipmaps.
  Поэтому уменьшение пиков RAM/CPU при загрузке **не реализовано**; возможен
  дополнительный временный буфер Half. Эта версия адресует прежде всего
  физические размеры GPU-текстур. На 8 ГБ iGPU результат ещё не подтверждён.
- Фильтрация соседних subtextures, швы, глубина, сторонние raw GL consumers,
  переключение шейдеров/разрешения и визуальный размер объектов нуждаются
  в настоящей игровой приёмке. Самостоятельные GL-кэши Viewpoint не очищаются.
- Никаких глобальных FMOD/listener, радио, checksum или сетевых изменений.
- Только для локального использования владельцем: **не коммитить игровые PNG,
  оригинальные packs/JAR, собранный Java JAR и итоговый ZIP**. В Git только
  собственный код, тесты, документация и генераторы.

## Сборка

Нужны Python 3.10+, Pillow, JDK 25 для чтения настоящих class files игры,
локальные оригинальные game/Viewpoint/ZombieBuddy JAR. Компиляция --release 17.

```bash
python3 scripts/viewpoint_half_assets.py \
  --game-dir /path/to/projectzomboid \
  --viewpoint-jar /path/to/Viewpoint.jar --output /outside/repo/half-assets
python3 scripts/viewpoint_half_build.py \
  --game-jar /path/to/projectzomboid.jar --buddy-jar /path/to/ZombieBuddy.jar \
  --viewpoint-jar /path/to/Viewpoint.jar --assets /outside/repo/half-assets \
  --jdk /path/to/jdk25 --output /outside/repo/SiegerViewpointHalf-CLIENT-TEST.zip
```

Выходные пути должны быть новыми. Генератор отказывается писать в исходники
или каталог Steam. Исходные packs проверяются на изменение во время сборки.

## Проверки на владельческом компьютере

| Проверка | Результат |
|---|---|
| Python: оба pack-формата, нечётный размер/padding, alpha, truncation, overwrite | PASS, 5 тестов |
| Все 546 PNG: SHA-256, размеры, PNG integrity | PASS |
| Компиляция по фактическим игровому и ZombieBuddy JAR | PASS |
| Настоящий ZombieBuddy: обнаружение 5 патчей и трансформация реальных целей | PASS |
| Настоящий FileTask_LoadPackImage, ImageData и mip chain | PASS |
| Сохранение логических размеров/оригинальной маски выбора | PASS |
| Half/Full в настоящем Viewpoint toggle и отдельном файле конфигурации | PASS |
| Новый изолированный JVM-запуск с сохранённым Full: оригинальные пиксели и галка Full | PASS |
| Несовпадающий asset manifest: адаптер отключается | PASS |
| Отдельный скрытый GPU-контекст RTX 3070: vanilla upload Half, readback, promotion Full без GL error | PASS |
| Повреждённая Half-страница сохраняет исходный Full pixel payload | PASS |
| Полная игровая картинка, Default/Vivid, перезапуск/переподключение | BLOCKED: требуется клиентская приёмка |
| A/B VRAM/RAM/FPS по одному маршруту | BLOCKED: требуется клиентская приёмка |
| Обычный MP-клиент с DoLuaChecksum=true | BLOCKED: требуется отдельная приёмка |
| Intel/AMD iGPU и 8 ГБ RAM | BLOCKED: нет измерения на целевом оборудовании |

Изолированная приёмка не подключается к работающей JVM. Реальные библиотеки
используются только из законно установленной игры, собственный cache направлен
в отдельный временный каталог; запуск всей игры и загрузка сохранения не нужны.
Unsafe используется только тестовым стендом для создания FileTask без worker
infrastructure; отгружаемый мод не использует Unsafe. GPU-проверка дополнительно
вызывает настоящий FileTask через настоящий FileSystemImpl.

```bash
python3 tests/test_viewpoint_half_assets.py
python3 scripts/viewpoint_half_engine_check.py \
  --game-jar /path/to/projectzomboid.jar --buddy-jar /path/to/ZombieBuddy.jar \
  --viewpoint-jar /path/to/Viewpoint.jar --jdk /path/to/jdk25 \
  --package /outside/repo/SiegerViewpointHalf-CLIENT-TEST.zip \
  --work-dir /new/isolated/check-dir --gpu
# Отдельный новый check-dir для негативной проверки; меняется только копия manifest:
# ... --work-dir /new/isolated/negative-check-dir --negative
```

## Установка для клиентской приёмки

Закрыть игру полностью, распаковать папку SiegerViewpointHalf в Zomboid/mods,
включить мод вместе с Viewpoint/ZombieBuddy, одобрить Java-пакет в ZombieBuddy.
Сначала одиночный мир; не навязывать мод игрокам активного сервера.
В console.txt проверить `ready`, `session=HALF`, `pages`, отсутствие неожиданных
fallback. Затем визуальная проверка пола, стен, деревьев, предметов, выбора мышью,
первого/третьего лица и Default/Vivid. Для Full снять галку и полностью закрыть
и открыть клиент. Для удаления отключить этот мод и перезапустить клиент;
оригинальные Steam-ресурсы остаются на месте. Автоматической установки нет.
