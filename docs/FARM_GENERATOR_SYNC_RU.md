# Генератор: единственная передача объекта клиентам

В story_test после live-установки генератора клиент передавал индекс 3,
но сервер имел единственный IsoGenerator с индексом 2. В логах:
`Can't find object index [3] for square [9288] [7759] with size [3]`,
затем `ISPlugGenerator.complete: setConnected of non-table: null` и
`ISAddFuel.complete: getMaxFuel of non-table: null`.

В настоящем закреплённом JAR Build 42.21.0 конструктор
`IsoGenerator(InventoryItem,IsoCell,IsoGridSquare)` вызывает
`AddSpecialObject`, затем при GameServer.server —
`transmitCompleteItemToClients`. Наш повторный полный transmit удалён.
Метка сцены, записанная после конструктора, отправляется через
унаследованный `IsoObject.transmitModData()`. Не меняем ванильные действия,
checksum, топливо, сохранения или существующие receipts.

Lua fixture моделирует реальную отправку из конструктора: суммарно ровно
одна полная отправка на каждый объект и отдельная отправка метки генератора.
Старая реализация даёт лишнюю полную отправку и проваливает regression.
Lua 5.1 и Kahlua из установленного игрового JAR проходят (модели объектов,
не доказательство сетевой приёмки). Python plan17/setup29/site6/camp12 PASS
под Python 3.11; системный 3.10 не поддерживает TestCase.enterContext.

После обновления необходим согласованный рестарт и одинаковый полный
SiegerAdmin у клиента и сервера при DoLuaChecksum=true. Существующий
генератор не пересоздаётся: подключение получает его из сохранённой клетки.
Ручная приёмка: Connect Generator, заправка и включение, а также создание
нового генератора при подключённом клиенте без перезахода. Эти проверки
пока PENDING; присутствие объекта в AreaScan их не заменяет.
