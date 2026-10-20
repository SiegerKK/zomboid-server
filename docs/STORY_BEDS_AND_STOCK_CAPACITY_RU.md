# Кровати и вместимость складов — продолжение PR #29

Изменения расширяют существующие `story build`, `story batch` и AreaScan.
Нового движка сценариев, сервиса, таймера или клиентского канала нет.
Это исходники и тесты: развёртывание и приёмка на реальном B42.21 не выполнены.

## Нативные спальные места

Одна операция `place/bed` создаёт один настоящий `IsoObject` из установленного
`IsoSprite`. На этапе preflight проверяется нативное свойство **BedType**:
принимаются только `badBed`, `averageBed` или `goodBed`, не свойства стула.
Глобальные свойства спрайта не переписываются. Клетка должна быть загружена,
иметь существующий пол и не содержать конфликтующую мебель/стену/жителя.

```json
{"id":"cot_head","op":"place","kind":"bed",
 "at":[100,200,0],"sprite":"furniture_bedding_01_10"}
```

Это пример синтаксиса, не утверждённая точка или гарантированный спрайт.
Без `bed_type` принимается установленное нативное качество кровати.
Необязательный `bed_type: "averageBed"` требует точного совпадения.
Невалидный спрайт отменяет весь этап до первой записи; декоративной подмены нет.

Многоклеточная кровать описывается отдельной операцией для каждой её клетки.
Подбирать надо полный согласованный набор спрайтов, а не размножать изголовья.
Все части одного нового спального места включайте в один этап. Имена действий
дают обычные метки `settlement:stage:action`; новый реестр кроватей не вводится.
Проверка мебели и свободного подхода по снимку не заменяет игровую проверку
ориентации, коллизии и того, что клиент предлагает действие сна.

AreaScan сообщает `bed_type` для объектов с соответствующим нативным свойством,
включая исходную мебель. `build verify` для новых кроватей требует совпадения
класса, спрайта, метки и нативного качества. Старый скан без этого поля не
доказывает работоспособность. Параметры сервера, разрешающие сон в multiplayer,
не меняются. Крыша, тепло, защита от дождя, безопасный проход и сохранение после
рестарта остаются отдельными предметами приёмки; кровать не превращает каркас
без крыши в законченный жилой дом.

## Вместимость при снабжении

У существующего `container/add` теперь проверяется **суммарный входящий вес**
всего пакета для каждого реального контейнера. Обращения по индексу и по
`construction_tag` к одному ящику используют общий расчёт. Ограничение задаёт
нативный `ItemContainer:hasRoomFor(nil, weight)`, а не число предметов или
задуманная автором вместимость. Вес берётся из `InventoryItem:getUnequippedWeight()`.

Для жидкости сначала создаётся и наполняется **отдельный, ещё не размещённый**
образец. Его фактические тип, объём и вес проверяются до первой записи в мир.
Таким образом, ошибка второй строки с водой не оставляет первую выдачу
предметов уже выполненной. Суммарная проверка учитывает вес заполненных ёмкостей.
Перед каждым добавлением вместимость проверяется повторно; исчезнувший или
подменённый целевой контейнер не получает выдачу через старую ссылку.

Запланированные удаления **не засчитываются как заранее освободившееся место**.
Когда выдача помещается только после освобождения ящика, сначала выполните
отдельное удаление, проверьте результат и затем новый пакет добавления.
Старая семантика выдачи игрокам, машине и на землю не изменена; эта проверка
добавлена для мировых контейнеров, используемых сценариями снабжения.

Неизвестная вместимость/вес, неподходящий нативный тип жидкости или переполнение
отклоняются, а не заменяются догадкой. Без наблюдений из установленной игры
нельзя утверждать, что конкретная ведомость действительно вмещается в шкаф.
Повторное применение успешного `batch` по-прежнему повторно выдаёт предметы:
нового автоматического пополнения или стадийного журнала batch здесь нет.

## Ошибка после начала применения

В `build` исправлена классификация сбоя первой операции: нативный объект может
появиться, а отправка клиентам — завершиться ошибкой, при счётчике `applied=0`.
Такой ответ теперь содержит `partial_possible`, а не `preflight_failed`.
Автоматического отката или безопасного повторения не обещается.

## Проверка

При проверке установленного JAR B42.21 исправлено чтение флагов коллизии:
`PropertyContainer.has(IsoFlagType)` используется раньше старого `Is`.
Если доступных методов нет, размещение на ребре запрещается, а не пропускает
проверку. Регрессия моделирует нативную стену с `has(collideN)` и отказ при
недоступном API. Python-чтение предыдущего batch-запроса также закрывает
файл через context manager, без ResourceWarning.

Расширены существующие Python- и Lua-тесты: BedType, отсутствие пола,
неподходящая вторая часть кровати, постпроверка спрайта без BedType,
суммарное переполнение, заполненные жидкости, алиасы index/tag,
недоступный API вместимости и сбой сетевой отправки первой операции.
Локальный прогон использует Python и установленную библиотеку Lua 5.4;
штатный GitHub CI отдельно выполняет Lua 5.1 и проверку зеркал SiegerAdmin.
Это модельные игровые объекты, не доказательство игровой приёмки.

Основания для нативных вызовов: публичные Java API ItemContainer
(`hasRoomFor`), InventoryItem (`getUnequippedWeight`) и PropertyContainer
(`Val`), а также опубликованный vanilla Lua
`ISWorldObjectContextMenu.getBedQuality`, читающий `BedType` через `get`.
Различие `get`/`Val` обрабатывается по наличию метода; при отсутствии обоих
постройка не разрешается. Код установленного B42.21 всё равно требует приёмки.


## Native B42 shipment item compatibility

Checked installed 42.21 scripts declare `Base.TinnedBeans`, `Base.TinnedSoup`,
`Base.Torch`, `Base.WateredCan`, `Base.WaterBottle` and `Base.PetrolCan`.
Legacy/example IDs CannedBeans, CannedSoup, Flashlight, WateringCan,
WaterBottleEmpty and EmptyPetrolCan must not be assumed valid prototypes.
Owner-private supply files are corrected separately; no private map data is
published. Native bottles/cans can have initial fluid from their script.
For an explicit fluid shipment the runtime clears ONLY its freshly created,
detached prototype/item with native FluidContainer.Empty(), then verifies
zero amount, capacity, requested litres and actual native primary fluid before
normal container replication. Existing world inventory is never emptied.
Missing Empty API fails during full preflight, before world mutation.
Lua fixtures cover prefilled defaults and absent API; actual dedicated-server
shipment acceptance is still separate.


## Stable existing storage after barricade insertion

Real first-stage acceptance exposed native object-index shifts: a new barricade
can be inserted before existing furniture. Its build receipt completed, while
all supplies failed full preflight with zero applied. The old setup journal
remains a failed attempt; it must not be erased or adopted as successful.

Container batches now accept exactly ONE selector: object_index,
construction_tag, or object_sprite. The new object_sprite is an exact native
sprite name on the exact requested X/Y/Z, in the square collection only.
Both survey preflight and server preflight require a unique matching object;
the actual container index/type and full cumulative capacity still match.
The server re-resolves and compares the same native container before applying.
A missing sprite or duplicate match fails closed; no nearest-object fallback.
Existing indices keep their strict semantics. Planned new crates retain their
existing construction_tag selectors. No arbitrary Lua or new network service.

Private plans can switch existing selectors only after mapping their original
index to the uniquely observed sprite in a verified current scan. This is
not an automatic migration of arbitrary historical plans. Fixtures cover an
inserted preceding object and ambiguity; live retest is a separate gate.


## Capacity diagnostics and explicit rejected-stock redistribution

AreaScan container records optionally expose actual native `capacity`,
`capacity_weight` and `free_capacity`; item records expose
`unequipped_weight` where available. Missing/failed getters stay absent, never
become fabricated free space. Only existing requested scans collect this data.
Batch preflight logs identify the failed action ordinal and capacity details.

`pz story build setup WORLD ... --retry-stock --yes` is a separate explicit
operator action after a definitive stock **preflight_failed, applied=0**.
It requires the unchanged confirmed native build and matching previous request,
a fresh post-build survey, a valid baseline and the old immutable shipment.
Only redistribution between containers is allowed: every item/count/fluid
and all ground actions must remain unchanged. The previous failed request,
receipt and shipment are retained in a separate audit JSON. Completed build
is not replayed; the corrected shipment gets one new request ID. Unknown,
pending, partial_possible or nonzero-applied outcomes cannot be retried.
Normal resume still polls only the original request and never retries a failure.
A crash during explicit repair may require manual inspection; journals must
not be deleted or manually marked successful. No automatic retry/rollback.
