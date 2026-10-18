# Инцидент профиля персонажа: экипировка не работает, затем disconnect

Дата испытания: 18 октября 2026. Среда: существующий `story_test`, dedicated Build **42.21.0**.
Проверенный код на момент последней попытки: `cba2f7cfc8e59f35a500411180ab8e49fb8ae5f3`,
клиентский handshake `radio-char16`, PR #27.

**Результат игровой приёмки: FAIL. Не применять профиль повторно и не мержить эту реализацию.**
Отчёт описывает установленную причину и требования к исправлению; исправление inventory pipeline
в этом коммите НЕ реализовано и НЕ развёрнуто. Во время расследования выполнялись только чтение
и сохранение приватных доказательств, без игровых мутаций, рестарта или изменения защиты.

## 1. Что произошло

1. Read-only аудит после прежнего permission kick показал исходное состояние персонажа:
   новых профильных предметов, травм и сохранённого marker не было.
2. Попытка char15 остановилась **до записей** в initial API assertion: Java-метод
   `NetworkPlayerAI.updateXpChecker` не был доступен из Lua.
3. Char16 прошёл PREPARE → server baseline → client COMMIT. Клиент прислал `client_applied`,
   нужные счётчики предметов/навыков и marker `complete`. Был выполнен RCON save.
4. Настоящий игрок не смог экипировать ни одно выданное оружие. В журналах сервера появились
   отсутствующие item references и ошибка обработки SyncItemFields.
5. Затем соединение было разорвано. Точная причина **этого** disconnect — лимит пинга,
   а не прежний Capability/ChangePlayerStats отказ.

Ответ `client_applied` доказал только изменение клиентской копии. Он не доказывал,
что сервер знает новые item ID, что работают server-authoritative timed actions,
что предметы можно экипировать или что состояние сохранится после relog.
Предыдущую оценку применения как завершённого следует считать отозванной.

## 2. Подтверждённые доказательства

### Предметы не находятся на сервере

В `2026-10-18_21-49_DebugLog-server.txt` наблюдались сообщения:

```text
PlayerAttachedItemPacket.processServer item can't be found
SyncItemFieldsPacket.parse(SyncItemFieldsPacket.java:383)
java.lang.NullPointerException: Cannot invoke "zombie.inventory.InventoryItem.hasSharpness()" because "item" is null
```

В исследованном окне найдено восемь сообщений `item can't be found`. Полные строки
с ContainerID, идентификаторами подключения и персональными данными в Git не включены.
Это ошибка обработки сетевого пакета; падение всего процесса/VPS этими записями не доказано.

### Последний disconnect: ping limit

Connection log и клиентский журнал согласованы:

```text
21:54:47.073  event="kick" message="UI_OnConnectFailed_Ping"
21:54:47.073  event="force-disconnect" message="kick-ping-limit"
ping: user "<redacted>" is disconnected because ping is too high ping=657
ReceiveKickedDisconnect: UI_OnConnectFailed_Ping
```

Фактические настройки на VPS:

```ini
PingLimit=400
DoLuaChecksum=true
AntiCheatPermission=2
AntiCheatXP=2
```

657 мс превышает настроенные 400 мс. Почему пинг вырос, **ещё не установлено**.
Причинная связь между packet errors и ростом пинга не измерялась. Нет оснований
объявлять этот последний kick повторением Capability, причиной нехватку RAM,
Viewpoint, радио или сеть без отдельных замеров.

### Предыдущий, отдельный permission kick

Для char14 зафиксировано `AntiCheatPermission`, reason `ChangePlayerStats: no capability`.
Это другой инцидент. В char15/16 клиентские `sendPlayerStatsChange` и `SyncXp` удалены.
Аннотация реального `PlayerXpPacket` также требует capability редактирования статистики.
Отключать проверки или выдавать обычному игроку роль администратора нельзя считать исправлением.

## 3. Ошибка реализации

В `mods/SiegerRadio/42/media/lua/client/SiegerStoryCharacterClient.lua` COMMIT:

- создаёт новые объекты через `instanceItem` на клиенте;
- удаляет прежние вещи через локальный `inv:Remove`;
- добавляет оружие и рюкзак через локальный `destination:AddItem`;
- локально заполняет рюкзак и вызывает equip/clothing sync, не подтвердив наличие
  соответствующих item ID и container ownership на сервере.

Предположение в комментарии о достаточности client-authoritative inventory для этой операции
оказалось неверным. Одних локального AddItem, OnClothingUpdated, ACK и RCON save недостаточно.
Сервер получает attachment/SyncItemFields с неизвестными ему предметами. Это согласуется
с невозможностью server-authoritative экипировки и напрямую подтверждается missing-item log.
Полный попарный снимок ID клиент↔сервер ещё не собран, поэтому не следует выдумывать
конкретные значения ID или объявлять все вложенные предметы одинаково повреждёнными.

`ISEquipWeaponAction.lua` в установленной игре ищет предмет по ID в inventory,
а не только по FullType. Существование картинки и правильный счётчик типа в клиенте
не означает исправный сетевой предмет.

### Штатный путь, проверенный по установленному JAR

В настоящем `projectzomboid.jar` Build 42.21.0:

- `AddItemCommand.Command` создаёт предметы в серверном inventory через
  `ItemContainer.AddItems`, затем отправляет владельцу `PacketType.AddItemInInventory`;
- `AddItemInInventoryPacket.write` сериализует эти экземпляры через `InventoryItem.save`;
- клиентский parser загружает сериализованный объект через `InventoryItem.load`,
  после чего `processClient` добавляет полученный экземпляр в inventory.

Это ориентир для корректного server-created / serialized-to-client пути.
Нельзя заменять его созданием второго независимого `instanceItem` на клиенте.
Внутренние классы PacketTypes не следует автоматически считать доступными из Lua:
требуется отдельно проверить Lua-exposed обёртку либо использовать штатный root/RCON
`additem` для первого минимального эксперимента.

Ранее также проверено: Lua globals `sendAddItemToContainer` и
`sendRemoveItemFromContainer` в этом JAR выполняют отправку только на сервере.
Их вызов на клиенте не исправляет рассинхронизацию.

## 4. Требования к нормальному исправлению

### Авторитет инвентаря и протокол

1. Сначала получить ограниченные read-only snapshots обеих сторон: item ID, FullType,
   owner, container path, condition, hand/worn/attached references и содержимое рюкзака.
   Все реальные снимки держать вне публичного Git. Проверять конкретного online player
   и выбранный world; не создавать предметы для неподтверждённого target.
2. Вынести выдачу и удаление из клиентского profile COMMIT. Предметы создавать **на сервере**
   и доставлять штатным проверенным механизмом с теми же ID. Состояние оружия и содержимое
   рюкзака формировать до сериализации, если используемый штатный путь это поддерживает.
   Вложенные контейнеры и сохранность их ID проверять отдельно.
3. Снятие предметов из рук/одежды/attachments и удаление выполнять согласованно через
   поддерживаемые B42 механизмы. Локальное Remove не заменяет серверное удаление.
   Нельзя удалять всё по FullType при возможных одинаковых легитимных предметах.
4. Не запускать auto-equip до подтверждения, что сервер и клиент находят один item ID
   в правильном контейнере. Для первой приёмки экипировать вручную через обычное меню игры.
5. Разделить результаты `client_applied`, `server_inventory_verified`,
   `native_action_verified`, `persisted_after_relogin`. `complete` не должен скрывать
   отсутствие обязательных подтверждений. Сверять ID/ownership, не только счётчики типов.
6. Вести durable per-action ledger и tags созданных предметов. Частичная ошибка остаётся
   `partial_possible`; запретить blind retry. Один последний guard и marker персонажа
   не являются доказательством доставки каждого предмета.
7. Перки, Stats и здоровье оставить отдельными контролируемыми операциями. Обычный клиент
   не должен отправлять привилегированные XP/ChangePlayerStats пакеты. Проверять именно
   Lua-exposed API и штатные Java bridges реальной сборки; Java public недостаточно.
8. Для ран диагностировать `bandaged`, `scratchTime`, `bleedingTime`, infection flags,
   а не только `scratched()`: `setBandaged(true,...)` очищает этот флаг, сохраняя wound timer.

### Восстановление уже затронутого персонажа

- Не применять весь профиль заново. Не откатывать мир и не удалять сохранения.
- Сначала после подключения снять snapshots с обеих сторон и определить, какие IDs
  существуют только локально, какие на сервере и какие уже записались в player data.
- Для каждого затронутого предмета подготовить адресный план сверки/замены. Сохранить
  легитимный инвентарь и текущий прогресс. Не назначать вручную произвольные client IDs
  серверным предметам и не заменять всё по имени типа.
- Повторный вход может изменить наблюдаемую картину, но его нельзя выдавать за доказанное
  исправление pipeline. Нужны native equip, transfer и сохранение после следующего relog.

## 5. План игровой приёмки перед новой выдачей полного комплекта

Начать с **одного** обычного предмета/оружия через штатный server-created путь,
с согласованными изменениями на существующем story_test, не с повторения полного профиля.

| Проверка | Критерий |
|---|---|
| Обычный игрок | Нет role grant, DoLuaChecksum/AntiCheatPermission/XP включены |
| Создание | Один серверный ID, сериализованный экземпляр у нужного клиента |
| Сверка | ID, FullType, condition, owner и container совпадают |
| Экипировка | Ручные equip/unequip завершаются; ID находится на сервере |
| Использование | Для оружия работают подходящие reload/unload; выстрел — только в согласованном месте |
| Перенос | Перекладывание main inventory↔рюкзак проходит на обеих сторонах |
| Репликация | Второй клиент видит экипированное оружие; не подменять это серверным ACK |
| Сохранение | После штатного сохранения и relog тот же предмет/ID/condition без дубликатов |
| Повтор/рестарт | Тот же action ID не создаёт второй предмет, uncertain не повторяется автоматически |
| Негативный путь | Нет target/API/доставки → явная ошибка, без повторной массовой выдачи |
| Журналы | Нет missing-item, SyncItemFields NPE, permission/XP kick |
| Пинг | Одновременно измерены клиентский ping и server tick/нагрузка; причина ping spike определяется отдельно |

После минимального PASS расширять тест: один рюкзак → вложенный предмет →
точечное удаление → набор. Новые item IDs и реальные inventories не публиковать.
Автоматический CI дополняет эту приёмку, но не заменяет её.

## 6. Статус функций после инцидента

| Функция | Статус | Основание |
|---|---|---|
| Read-only character audit | PASS ограниченно | Реальный клиент вернул bounded отчёт; нет полной сверки ID |
| char14 unprivileged profile | FAIL | Capability / ChangePlayerStats kick |
| char15 direct AI baseline | FAIL | Lua не экспонирует updateXpChecker; отказ до мутаций |
| char16 server baseline / client ACK | PASS ограниченно | Был достигнут client_applied, это не приёмка инвентаря |
| char16 inventory ownership / equip | **FAIL** | Пользователь не экипирует; missing-item и SyncItemFields NPE |
| Сохранение персонажа после relog | BLOCKED | Не выполнена сверка; RCON save не доказывает persistence |
| Двухклиентная репликация | BLOCKED | Не проверялась |
| Причина последнего disconnect | PASS диагностика | Connection log: kick-ping-limit, 657 мс при PingLimit=400 |
| Причина роста пинга | BLOCKED | Нет синхронного профиля RTT/server tick |
| Готовность character profile к merge | **FAIL** | Инвентарный pipeline требует переработки |

## 7. Выполненные действия и границы расследования

Выполнялись `pz story character status story_test`, чтение `docker logs`,
read-only чтение DebugLog/connection logs и безопасно выбранных INI ключей;
сопоставление с клиентским `ReceiveKickedDisconnect`;
`javap -c -p` по установленному игровому JAR для AddItemCommand,
AddItemInInventoryPacket и LuaManager.GlobalObject;
чтение штатного ISEquipWeaponAction.lua. Живой request/guard не переотправлялся.

Полные доказательства сохранены в root-only каталоге VPS
`/srv/zomboid/manager/joel-arrival/char16-equip-incident` (каталог 700, файлы 600).
Публичный отчёт не содержит IP/SteamID/логина игрока, координат баз,
полного инвентаря, сохранений, секретов или бинарных игровых файлов.

После сообщения пользователя **не** выполнялись новая выдача, удаление вещей,
рестарт, restore, Workshop update, изменение сети/защиты либо merge.
