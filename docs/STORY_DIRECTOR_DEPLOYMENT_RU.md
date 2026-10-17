# Story Director: фактическая проверка 17 октября 2026

Рабочая интеграция находится в PR #6 (`fix/story-director-road-home-integration`).
Основа Story — main `2ded010c2e65d752dbb94fa362336c94ea1a5974`.
Сохранены все игровые Compose/config/scripts из развёрнутого PR #4
`f276a3a1a0f1fa3e389d40ea31a99eb5f95879e8`: полный VERSION=6 Sandbox,
контракт точных Workshop-исходников и runtime-аудит TLOU. Main без этих
исправлений поверх VPS не устанавливался. PR #6 не объединён автоматически.

**Итог окна:** `road_home` возвращён в работающее состояние, RCON отвечает,
native settings/registry audit прошёл. `PAUSE_EMPTY=true`, 6 прежних модов,
лимит 12 GiB сохранены; Story mount отсутствует. Внешние IPv4 UDP 16261
(A2S) и 16262 (RakNet) отвечают, server password flag=0. TCP RCON/DB/Docker
не отвечают извне и не опубликованы Docker. IPv6 с этой локальной машины
не проверен: нет маршрута. `story_test` и restored copy остановлены.
Доступ к клинике клиентом и реальное применение сцены **ещё не проверены**.

## Данные и изоляция

- До копирования RCON подтвердил `Players connected (0):`.
- `pz stop --yes` штатно остановил игру с exit code 0.
- Cold backup оригинала:
  `/srv/zomboid/backups/worlds/road_home/world-20261017T060831Z-58424.tar.gz`.
  Его SHA-256 проверен. `pz load` восстановил архив в новый слот `story_test`.
- Для 7215 файлов данных проверены совпадающие SHA-256 и разные inode.
  Никаких hardlink с оригиналом и переноса/удаления исходного мира нет.
- После первого тестового запуска создан и проверен cold backup:
  `/srv/zomboid/backups/worlds/story_test/world-20261017T061757Z-65088.tar.gz`.
  Восстановлен в `story_test_restore_check`: 7219 файлов данных совпали,
  inode независимы. Story bundle в восстановленной копии автоматически
  переименован в `bundle.lua.needs-review` и не активен.
- У `road_home` нет `story/bundle.lua`. Обновление кода не добавляет в него
  сценарий, runtime mount или предметы. `.env` сохранён без изменений.
- Образ, Workshop snapshot и Java agent не обновлялись. RCON наружу не открыт.
- Перед возвратом основного мира все **7219 файлов** `road_home/data`
  повторно сравнили с манифестом, снятым после его остановки: SHA-256 и
  набор путей полностью совпали. Испытания тестового слота их не изменили.
- После второго запуска тест штатно остановлен с exit code 0; сохранён ещё
  один cold backup `story_test/world-20261017T062247Z-66614.tar.gz`.

## Проверки кода

Пройдены root smoke manager, `bash -n`, Python Story tests, Story Compose test,
тест генератора Sandbox, Workshop audit и реальный source-contract test.
Lua 5.1 успешно разбирает runtime; behavioral harness проверяет записку,
контейнер, повторную загрузку, частично завершённую выдачу и отказ до мутации.
Это **моделирование**, а не подтверждение сетевой синхронизации клиентами.
CI run 53 (`39009315745`) на commit `8ecf209` успешен.

По классам `projectzomboid.jar` именно закреплённой 42.21.0 проверены:
`instanceItem`, `Literature.addPage(Integer,String)`, `setCanBeWrite`,
`setNumberOfPages`, `seePage`, `AddWorldInventoryItem`, `transmitModdata`,
`sendAddItemToContainer(ItemContainer,InventoryItem)`,
`IsoBarricade.AddBarricadeToObject` и `addPlank(character,item)`.
Bytecode `sendAddItemToContainer` подтверждает ветку GameServer и рассылку
для контейнера с IsoObject-parent, а не только для инвентаря игрока.
Штатный `MOBarricade.lua` использует ту же пару вызовов создания/досок.

Исправления интеграции:

- `preview` принимает короткое имя сцены из документации.
- Ошибка Docker не считается доказательством остановленного сервера.
- У `Base.Note` из B42 по умолчанию `ReadType=photo`; для штатного меню чтения
  установлены `canBeWrite=true` и число страниц, а не только `addPage`.
- Проверка container-sync API выполняется до добавления предмета.
- Перед стартом bundle сравнивается с заново скомпилированными reviewed JSON
  и inspection metadata. Несовпадение блокирует старт.
- Повторный backup/restore уже отключённого Story bundle работает и не
  активирует старую сцену в новом слоте.
- Инспектор выводит токены созданных Story-предметов, чтобы различать их
  при проверке повторного входа и перезапуска.
- Runtime содержит in-memory preflight API без добавления предметов в мир.

Второй полный запуск `story_test` в настоящей игровой JVM подтвердил:
`SIEGER_STORY_API Base.Note pages/readability and container sync API available`
и `SIEGER_STORY_READY world=story_test scenes=0 read_only_probes=25`.
`SIEGER_STORY_ERROR` и `SIEGER_STORY_APPLIED` отсутствовали. Настоящий
`pz story apply story_test clinic_last_shift --yes` отказал с сообщением о
disabled draft, ничего не разместив. Реестр Forge/TLOU повторно проверен
на точном snapshot в server/client harness: только Runner/Stalker/Clicker
с весами 560/330/110 и callbacks HideIndoors для последних двух.
В общих startup-логах сохраняются прежние предупреждения ActionSystem/UI
и сообщения WorldGen о tile property (в том числе WindowShape), наблюдавшиеся
ещё при загрузке road_home до Story. Они не объявляются исправленными;
полный запуск и готовность RCON проверяются отдельно от этих сообщений.

## Место для проверки и участие клиента

Клиника найдена в **файлах карты закреплённого образа**, не по карте B41.
`media/maps/Muldraugh, KY/12_47.lotheader`, SHA-256:
`60affb122d6f73dae8965be5e4134b1d13b7eaa209dae2b01326a8a1d2a1f13e`.
В этом header комната №17 называется `edclinic`, уровень 0,
rectangle `(3175,12113,6,7)`: X=3175–3180, Y=12113–12119.
Формат чтения проверен по `IsoMetaGrid$MetaGridLoaderThread` и `IsoLot`
из того же JAR: little-endian числа, строки с переводом строки,
размер map-cell 256. Номер комнаты **не является индексом объекта**.
Глобальный поисковый проход встретил отдельный повреждённый/неполный header
`42_39.lotheader`; результаты по нему не использовались.

В `story_test` установлены только 25 read-only probes:
X=3175–3179, Y=12113–12117, Z=0. Первый полный запуск подтвердил
`SIEGER_STORY_READY world=story_test scenes=0 read_only_probes=25`.
При отсутствии игрока этот чанк не загружается; exact container/window
selectors пока не получены. Готовность runtime не означает применения сцены.

`clinic_last_shift.json` направлен только в `story_test` и **выключен**.
Подготовлены одна записка и небольшой запас (2 Bandage + 1 Disinfectant).
Дополнительная записка, баррикада, infected и decor выключены.
Лут не применяется без фактического selector. `pz story apply` настоящей
сцены ещё не выполнялся; предметы, текст в клиенте, сохранение этих предметов,
отсутствие дубликатов и баррикада требуют следующей проверки.

В согласованное окно переключить на тестовый слот при отсутствии игроков.
Игроку подключиться к тому же IP/порту и подойти к **3177,12116,0**
(при необходимости через admin UI Teleport). Сначала ничего не подбирать,
не переставлять шкафы и не ломать окна. Оператор получает
`SIEGER_STORY_INSPECT`, фиксирует реальные class/sprite/object_index,
штатно останавливает тест, делает `pz save story_test`, обновляет JSON через
PR и только затем применяет одну записку/лут. После проверки, рестарта и
повторного входа — отдельная сцена баррикады с новым scene ID и свежим
backup: уже staged scene нельзя тихо редактировать/повторно применять.

Команды оператора (остановка только после проверки игроков):

```bash
sudo pz story status road_home
sudo pz story status story_test
sudo pz story validate clinic_last_shift
sudo pz story preview clinic_last_shift
sudo pz stop --yes
sudo pz start story_test
# Посещение клиники клиентом, получение INSPECT, затем выход клиента.
sudo pz stop --yes
sudo pz save story_test
# После review точных selectors и enabled=true:
sudo pz story apply story_test clinic_last_shift --yes
sudo pz start story_test
```

Во время инспекции нельзя подключаться, предполагая, что это рабочий мир:
слоты используют один публичный endpoint; изменения на тесте не переносятся
обратно в road_home. Для завершения окна остановить тест и `pz start road_home`.

## Предложение по TLOU adapter — без реализации спавна

В точном Forge `GetTrueID` нормализует persistent outfit ID с учётом снятой
шапки. Клиентский `ISSpawnHordeUI_patch.lua` назначает `ZType` лишь в
`NonPersistentZData` при локальном spawn; MP-ветка отправляет обычный
`createhorde2` и возвращается до назначения типа. Поэтому этот debug UI
не является проверенным серверным адаптером специальных заражённых.

Будущий adapter должен работать только с зафиксированным source contract,
требовать готовый registry TLOU, хранить persistent соответствие
scene/action/trueID → ZType и иметь доказанный способ установки типа на
сервере и владельце zombie. Без такого способа — отказ, без vanilla fallback.
Создание, ownership transfer, смена шапки, unload/reload чанка, cold save,
restart, смерть/труп, внешний вид, урон и callbacks проверяются отдельно
двумя клиентами на копии. Повторный вход не должен возрождать уже убитых
сюжетных заражённых. Существующая таблица случайного выбора Forge и общая
популяция остаются неизменными. До этих тестов `infected` заблокирован.
